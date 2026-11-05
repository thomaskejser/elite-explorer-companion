use std::cell::RefCell;
use std::rc::Rc;

use windows::Win32::Foundation::{COLORREF, HWND, LPARAM, LRESULT, POINT, RECT, SIZE, WPARAM};
use windows::Win32::Graphics::Gdi::{
    AC_SRC_ALPHA, AC_SRC_OVER, BI_RGB, CreatePen, Ellipse, Polygon, IntersectClipRect, SelectClipRgn, LineTo, MoveToEx, PS_SOLID, BITMAPINFO, BITMAPINFOHEADER, BLENDFUNCTION, BeginPaint, CLIP_DEFAULT_PRECIS,
    CreateCompatibleDC, CreateDIBSection, CreateFontW, CreateSolidBrush, DEFAULT_CHARSET, DEFAULT_QUALITY,
    DIB_RGB_COLORS, DeleteDC, DeleteObject, EndPaint, FF_MODERN, FIXED_PITCH, FW_BOLD, FW_NORMAL, FillRect, GdiFlush,
    GetDC, GetTextExtentPoint32W, GetTextMetricsW, HDC, HFONT, HGDIOBJ, OUT_DEFAULT_PRECIS, PAINTSTRUCT, ReleaseDC,
    GetStockObject, NULL_BRUSH, SelectObject, SetBkMode, SetPixelV, SetTextColor, TEXTMETRICW, TRANSPARENT, TextOutW,
};
use windows::Win32::System::LibraryLoader::GetModuleHandleW;
use windows::Win32::UI::WindowsAndMessaging::{GetSystemMetrics, SM_CXSCREEN, SM_CYSCREEN};
use crate::prefs::{self, Prefs};
use windows::Win32::Graphics::Gdi::{GetMonitorInfoW, MONITOR_DEFAULTTOPRIMARY, MONITORINFO, MonitorFromWindow};
use windows::Win32::UI::Input::KeyboardAndMouse::{GetCapture, ReleaseCapture, SetCapture};
use windows::Win32::UI::WindowsAndMessaging::{
    CS_HREDRAW, CS_VREDRAW, CreateWindowExW, DefWindowProcW, GetCursorPos, GetWindowRect, HWND_TOPMOST,
    IDC_ARROW, LoadCursorW, RegisterClassExW, SW_HIDE, SW_SHOWNOACTIVATE, SWP_NOACTIVATE, SWP_NOMOVE, SWP_NOSIZE,
    SWP_NOZORDER, SetTimer, SetWindowPos, ShowWindow, ULW_ALPHA, UpdateLayeredWindow, WNDCLASSEXW, WS_EX_LAYERED,
    WS_EX_NOACTIVATE, WS_EX_TOOLWINDOW, WS_EX_TOPMOST, WS_POPUP,
};
use windows::core::{PCWSTR, w};

use crate::bands::{self, Family, Mark};
use crate::fss::ScreenBar;
use crate::spectrum::Tip;
use crate::win::screen;
use crate::win::vector::{self, Icon};
use crate::database::{MINIMAP_BLOCK_LY, MiniDensity};
use crate::exobio::{self, BodyLine, BodyList, Sheet};
use crate::jump::{self, HereLine, MapRoute, Panel, RoutePopup};
use crate::row::{ROW_SECTOR_UNNAMED, Row};
use crate::table::{TargetTable, light_years};
use crate::theme::*;

pub const TICK_TIMER: usize = 1;
pub const FLASH_TIMER: usize = 2;
pub const PULSE_TIMER: usize = 3;
pub const HYPER_TIMER: usize = 4;

const BD: i32 = 2;

fn colorref(c: Rgb) -> COLORREF {
    COLORREF(c.0 as u32 | (c.1 as u32) << 8 | (c.2 as u32) << 16)
}

fn dib_rgb(c: Rgb) -> u32 {
    (c.0 as u32) << 16 | (c.1 as u32) << 8 | c.2 as u32
}

fn mix(a: Rgb, b: Rgb, t: f64) -> Rgb {
    let m = |x: u8, y: u8| (x as f64 + (y as f64 - x as f64) * t).round() as u8;
    Rgb(m(a.0, b.0), m(a.1, b.1), m(a.2, b.2))
}

fn apply_alpha(pixels: &mut [u32], opacity: u8, backdrop: Option<&Backdrop>) {
    let key = dib_rgb(KEY);
    let band = dib_rgb(HEADER_BG);
    let band_alpha = (opacity as f64 * HEADER_ALPHA).round() as u32;
    let panel = dib_rgb(PANEL_BG);
    let panel_alpha = (opacity as f64 * PANEL_ALPHA).round() as u32;
    for (i, p) in pixels.iter_mut().enumerate() {
        let rgb = *p & 0x00ff_ffff;
        let under = backdrop.and_then(|b| b.pixels.get(i).copied());
        let a = if let Some((_, alpha, fade)) = under.filter(|(c, ..)| *c == rgb) {
            (opacity as f64 * alpha * fade).round() as u32
        } else if let Some((_, _, fade)) = under.filter(|(_, _, fade)| *fade < 1.0 && rgb != key) {
            (opacity as f64 * fade).round() as u32
        } else if rgb == key {
            0
        } else if rgb == band {
            band_alpha
        } else if rgb == panel {
            panel_alpha
        } else {
            opacity as u32
        };
        let scale = |shift: u32| ((rgb >> shift) & 0xff) * a / 255;
        *p = a << 24 | scale(16) << 16 | scale(8) << 8 | scale(0);
    }
}

fn wide(text: &str) -> Vec<u16> {
    text.encode_utf16().collect()
}

#[derive(Clone, Copy)]
struct Face {
    font: HFONT,
    char_w: i32,
    line_h: i32,
}

struct Fonts {
    row: Face,
    head: Face,
    small: Face,
    title: Face,
}

#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub enum Pane {
    Left,
    Top,
    Popup,
    Map,
    Plan,
    Marks,
    System,
    Coords,
}

impl Pane {
    fn name(self) -> String {
        format!("{self:?}").to_lowercase()
    }
}

#[derive(Clone, Copy, PartialEq, Debug)]
pub struct Style {
    pub font_pt: i32,
    pub scale: f64,
    pub opacity: f64,
    pub draggable: bool,
}

impl Style {
    pub fn of(pane: Pane, prefs: &Prefs, game_h: i32) -> Style {
        let drop = match pane {
            Pane::Left => SECTOR_FONT_DROP,
            Pane::Popup => 0,
            _ => TOP_FONT_DROP,
        };
        Style {
            font_pt: FONT_PT - drop,
            scale: hud_scale(game_h, prefs.size),
            opacity: if pane == Pane::Marks { 1.0 } else { prefs.opacity as f64 / 100.0 },
            draggable: prefs.draggable && matches!(pane, Pane::Left | Pane::Top | Pane::System | Pane::Coords),
        }
    }
}

pub fn hud_scale(game_h: i32, size_pct: u32) -> f64 {
    (game_h as f64 / REFERENCE_HEIGHT as f64).max(MIN_AUTO_SCALE) * size_pct as f64 / 100.0
}

pub struct Scene<'a> {
    pub nearest: &'a TargetTable,
    pub sector: &'a TargetTable,
    pub poi: &'a TargetTable,
    pub carrier_table: &'a TargetTable,
    pub plan_nearest: &'a TargetTable,
    pub clock: &'a str,
    pub carrier: &'a str,
    pub carrier_role: Role,
    pub neutron_plot: Option<&'a str>,
    pub here_line: HereLine,
    pub jump: Option<&'a Panel>,
    pub plan_sheets: &'a [Sheet],
    pub system_sheets: &'a [Sheet],
    pub coord_sheets: &'a [Sheet],
    pub system_list: Option<&'a BodyList>,
    pub popup: Option<&'a RoutePopup>,
    pub marks: Option<(ScreenBar, &'a [Mark], &'a [Tip])>,
    pub sectors: &'a [Row],
    pub density: Option<&'a MiniDensity>,
    pub route: MapRoute,
    pub lit: Option<[i64; 3]>,
    pub dots: &'a [(String, [f64; 3])],
    pub carrier_path: &'a [[f64; 3]],
    pub carrier_at: Option<[f64; 3]>,
    pub ship: Option<[f64; 3]>,
    pub ship_r: i32,
    pub hyper_glow: Option<f64>,
}

type BackdropCache = (MiniBox, [u64; 2], Rc<Backdrop>);

struct Backdrop {
    pixels: Vec<(u32, f64, f64)>,
}

#[derive(Clone, Copy, PartialEq)]
struct MiniBox {
    side: i32,
    gx: i32,
    gy: i32,
    w: i32,
    h: i32,
    edge: i32,
}

struct SheetBox {
    y: i32,
    cols: Vec<i32>,
    title_h: i32,
    head_h: i32,
    row_h: i32,
}

struct TableBox {
    x: i32,
    y: i32,
    cols: Vec<i32>,
    title_h: i32,
    head_h: i32,
    row_h: i32,
    width: i32,
    height: i32,
}

struct Layout {
    width: i32,
    height: i32,
    nearest: Option<TableBox>,
    sector: Option<TableBox>,
    poi: Option<TableBox>,
    carrier_table: Option<TableBox>,
    plan_nearest: Option<TableBox>,
    jump: Option<RouteBox>,
    sheets: Vec<SheetBox>,
    carrier_y: Option<i32>,
    popup: Option<PopupBox>,
    minimap: Option<MiniBox>,
    marks: Option<MarksBox>,
    system_list: Option<ListBox>,
}

impl Layout {
    fn sized(width: i32, height: i32) -> Layout {
        Layout {
            width,
            height,
            nearest: None,
            sector: None,
            poi: None,
            carrier_table: None,
            plan_nearest: None,
            jump: None,
            sheets: Vec::new(),
            carrier_y: None,
            popup: None,
            minimap: None,
            marks: None,
            system_list: None,
        }
    }
}

struct ListBox {
    row_h: i32,
    icon: i32,
    icon_gap: i32,
    name_x: i32,
    flag_x: i32,
    genus_cols: Vec<(Option<String>, i32)>,
    geo_x: i32,
    value_right: i32,
    width: i32,
    height: i32,
}

struct RouteBox {
    x: i32,
    w: i32,
    list_y: i32,
    row_h: i32,
    info: bool,
    height: i32,
}

#[derive(Clone, Copy)]
struct MarksBox {
    x: i32,
    y: i32,
    length: f64,
    pad: i32,
    row: i32,
}

struct PopupBox {
    name_w: i32,
    title_h: i32,
    row_h: i32,
}

pub struct Overlay {
    pub hwnd: HWND,
    pub pane: Pane,
    centre_x: Option<i32>,
    right_x: Option<i32>,
    bottom_y: Option<i32>,
    frame: Option<(i32, i32, i32, i32)>,
    backdrop: RefCell<Option<BackdropCache>>,
    icons: RefCell<Vec<Icon>>,
    fonts: Fonts,
    style: Style,
    draggable: bool,
    shown: bool,
    size: (i32, i32),
    drag: Option<(POINT, RECT)>,
    opacity: u8,
}

impl Overlay {
    pub fn create(
        style: Style,
        pane: Pane,
        wndproc: unsafe extern "system" fn(HWND, u32, WPARAM, LPARAM) -> LRESULT,
    ) -> Result<Overlay, String> {
        unsafe {
            let instance = GetModuleHandleW(None).map_err(|e| e.to_string())?;
            let class = WNDCLASSEXW {
                cbSize: std::mem::size_of::<WNDCLASSEXW>() as u32,
                style: CS_HREDRAW | CS_VREDRAW,
                lpfnWndProc: Some(wndproc),
                hInstance: instance.into(),
                hCursor: LoadCursorW(None, IDC_ARROW).unwrap_or_default(),
                lpszClassName: w!("EdOverlayHud"),
                ..Default::default()
            };
            RegisterClassExW(&class);
            let title_w: Vec<u16> = crate::app::TITLE.encode_utf16().chain(std::iter::once(0)).collect();
            let hwnd = CreateWindowExW(
                WS_EX_LAYERED | WS_EX_TOPMOST | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE,
                w!("EdOverlayHud"),
                PCWSTR(title_w.as_ptr()),
                WS_POPUP,
                0,
                0,
                10,
                10,
                None,
                None,
                Some(instance.into()),
                None,
            )
            .map_err(|e| e.to_string())?;
            let mut overlay = Overlay {
                hwnd,
                pane,
                centre_x: None,
                right_x: None,
                bottom_y: None,
                frame: None,
                backdrop: RefCell::new(None),
                icons: RefCell::new(Vec::new()),
                fonts: make_fonts(hwnd, style.font_pt, style.scale),
                style,
                draggable: style.draggable,
                shown: false,
                size: (0, 0),
                drag: None,
                opacity: (style.opacity.clamp(0.0, 1.0) * 255.0).round() as u8,
            };
            overlay.anchor();
            Ok(overlay)
        }
    }

    fn px(&self, v: i32) -> i32 {
        let scaled = (v as f64 * self.style.scale).round() as i32;
        if v > 0 { scaled.max(1) } else { scaled }
    }

    fn anchor(&mut self) {
        let (screen_w, screen_h) = unsafe { (GetSystemMetrics(SM_CXSCREEN), GetSystemMetrics(SM_CYSCREEN)) };
        let margin = self.px(EDGE_MARGIN);
        let game_h = screen::game_height().unwrap_or(screen_h);
        let centred = matches!(self.pane, Pane::Top | Pane::System | Pane::Coords);
        let default_x = match self.pane {
            _ if centred => screen_w / 2,
            Pane::Plan => screen_w - margin,
            _ => margin,
        };
        let default_y = match self.pane {
            Pane::Left => screen_h - margin,
            Pane::System => game_h * SYSTEM_MAP_TOP / REFERENCE_HEIGHT,
            Pane::Coords => game_h * GALAXY_MAP_TOP / REFERENCE_HEIGHT,
            _ => margin,
        };
        let (x, y) = prefs::place(&self.pane.name())
            .filter(|(x, y)| (0..screen_w).contains(x) && (0..screen_h).contains(y))
            .unwrap_or((default_x, default_y));
        self.centre_x = centred.then_some(x);
        self.right_x = (self.pane == Pane::Plan).then_some(x);
        self.bottom_y = (self.pane == Pane::Left).then_some(y);
        unsafe {
            let _ = SetWindowPos(self.hwnd, Some(HWND_TOPMOST), x, y, 0, 0, SWP_NOSIZE | SWP_NOACTIVATE);
        }
        self.size = (0, 0);
    }

    pub fn restyle(&mut self, style: Style) {
        if style == self.style {
            return;
        }
        let moved = style.scale != self.style.scale;
        delete_fonts(&self.fonts);
        self.fonts = make_fonts(self.hwnd, style.font_pt, style.scale);
        self.style = style;
        self.draggable = style.draggable;
        self.opacity = (style.opacity.clamp(0.0, 1.0) * 255.0).round() as u8;
        if moved {
            self.anchor();
        }
        self.size = (0, 0);
    }

    pub fn start_timer(&self, id: usize, ms: u32) {
        unsafe {
            SetTimer(Some(self.hwnd), id, ms, None);
        }
    }

    pub fn stop_timer(&self, id: usize) {
        unsafe {
            let _ = windows::Win32::UI::WindowsAndMessaging::KillTimer(Some(self.hwnd), id);
        }
    }

    pub fn set_visible(&mut self, visible: bool) -> bool {
        if visible == self.shown {
            return false;
        }
        unsafe {
            if visible {
                let _ = ShowWindow(self.hwnd, SW_SHOWNOACTIVATE);
                let _ = SetWindowPos(
                    self.hwnd,
                    Some(HWND_TOPMOST),
                    0,
                    0,
                    0,
                    0,
                    SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE,
                );
            } else {
                let _ = ShowWindow(self.hwnd, SW_HIDE);
            }
        }
        self.shown = visible;
        true
    }

    pub fn is_shown(&self) -> bool {
        self.shown
    }

    pub fn fit_above(&mut self, below: &Overlay) {
        unsafe {
            let mut r = RECT::default();
            let _ = GetWindowRect(below.hwnd, &mut r);
            let mut screen = MONITORINFO { cbSize: std::mem::size_of::<MONITORINFO>() as u32, ..Default::default() };
            let _ = GetMonitorInfoW(MonitorFromWindow(below.hwnd, MONITOR_DEFAULTTOPRIMARY), &mut screen);
            let gap = self.px(EDGE_MARGIN);
            let top = screen.rcMonitor.top + gap;
            let frame = Some((r.left, top, (r.right - r.left).max(1), (r.top - gap - top).max(1)));
            if frame != self.frame {
                self.frame = frame;
                self.size = (0, 0);
            }
        }
    }

    pub fn refresh(&mut self, scene: &Scene) {
        let layout = self.layout(scene);
        if let (Pane::Marks, Some(b)) = (self.pane, layout.marks) {
            self.size = (layout.width, layout.height);
            unsafe {
                let _ = SetWindowPos(self.hwnd, None, b.x, b.y, layout.width, layout.height, SWP_NOZORDER | SWP_NOACTIVATE);
            }
            self.render(scene);
            return;
        }
        if let (Some((x, y, ..)), Pane::Map) = (self.frame, self.pane) {
            if (layout.width, layout.height) != self.size {
                self.size = (layout.width, layout.height);
                unsafe {
                    let _ = SetWindowPos(self.hwnd, None, x, y, layout.width, layout.height, SWP_NOZORDER | SWP_NOACTIVATE);
                }
            }
            self.render(scene);
            return;
        }
        if (layout.width, layout.height) != self.size {
            self.size = (layout.width, layout.height);
            if self.pane == Pane::Popup {
                unsafe {
                    let x = (GetSystemMetrics(SM_CXSCREEN) - layout.width) / 2;
                    let screen_h = GetSystemMetrics(SM_CYSCREEN);
                    let y = (screen_h * 3 / 4 - layout.height / 2).min(screen_h - layout.height).max(0);
                    let _ = SetWindowPos(self.hwnd, None, x, y, layout.width, layout.height, SWP_NOZORDER | SWP_NOACTIVATE);
                }
                self.render(scene);
                return;
            }
            let anchor_x = match (self.centre_x, self.right_x) {
                (Some(cx), _) => Some(cx - layout.width / 2),
                (None, Some(rx)) => Some(rx - layout.width),
                _ => None,
            };
            unsafe {
                match anchor_x {
                    Some(x) => {
                        let mut r = RECT::default();
                        let _ = GetWindowRect(self.hwnd, &mut r);
                        let _ = SetWindowPos(
                            self.hwnd,
                            None,
                            x,
                            r.top,
                            layout.width,
                            layout.height,
                            SWP_NOZORDER | SWP_NOACTIVATE,
                        );
                    }
                    None => match self.bottom_y {
                        Some(bottom) => {
                            let mut r = RECT::default();
                            let _ = GetWindowRect(self.hwnd, &mut r);
                            let top = bottom - layout.height;
                            let _ = SetWindowPos(self.hwnd, None, r.left, top, layout.width, layout.height, SWP_NOZORDER | SWP_NOACTIVATE);
                        }
                        None => {
                            let _ = SetWindowPos(
                                self.hwnd,
                                None,
                                0,
                                0,
                                layout.width,
                                layout.height,
                                SWP_NOMOVE | SWP_NOZORDER | SWP_NOACTIVATE,
                            );
                        }
                    },
                }
            }
        }
        self.render(scene);
    }

    fn text_w(&self, face: Face, text: &str) -> i32 {
        unsafe {
            let dc = GetDC(Some(self.hwnd));
            let old = SelectObject(dc, HGDIOBJ(face.font.0));
            let mut size = SIZE::default();
            let w = wide(text);
            let _ = GetTextExtentPoint32W(dc, &w, &mut size);
            SelectObject(dc, old);
            ReleaseDC(Some(self.hwnd), dc);
            size.cx
        }
    }

    fn label_w(&self, face: Face, text: &str, padx: i32) -> i32 {
        self.text_w(face, text) + 2 * padx + 2 * BD
    }

    fn label_h(face: Face) -> i32 {
        face.line_h + 2 + 2 * BD
    }

    fn table_box(&self, t: &TargetTable) -> TableBox {
        let pad = self.px(PAD_X / 2);
        let f = &self.fonts;
        let cols: Vec<i32> = t
            .columns
            .iter()
            .map(|c| {
                let data = c.width as i32 * f.row.char_w + 2 * pad + 2 * BD;
                let head = (c.width as i32 * f.head.char_w + 2 * pad + 2 * BD)
                    .max(self.label_w(f.head, c.heading, pad));
                data.max(head)
            })
            .collect();
        let grid_w: i32 = cols.iter().sum();
        let title_h = if t.title.is_some() { Self::label_h(f.title) } else { 0 };
        let title_w = t.title.as_deref().map_or(0, |s| self.label_w(f.title, s, 1));
        let head_h = Self::label_h(f.head);
        let row_h = Self::label_h(f.row) - if self.pane == Pane::Left { SECTOR_ROW_TRIM } else { 0 };
        TableBox {
            x: 0,
            y: 0,
            cols,
            title_h,
            head_h,
            row_h,
            width: grid_w.max(title_w),
            height: title_h + head_h + row_h * t.shown_rows() as i32,
        }
    }

    fn layout(&self, scene: &Scene) -> Layout {
        match self.pane {
            Pane::Left => self.layout_left(scene),
            Pane::Top => self.layout_top(scene),
            Pane::System => self.layout_system(scene),
            Pane::Coords => self.layout_coords(scene),
            Pane::Popup => self.layout_popup(scene),
            Pane::Map => self.layout_map(scene),
            Pane::Plan => self.layout_plan(scene),
            Pane::Marks => self.layout_marks(scene),
        }
    }

    fn layout_plan(&self, scene: &Scene) -> Layout {
        let gap = TOP_TABLE_GAP * self.fonts.row.char_w;
        let plan_nearest = scene.plan_nearest.visible.then(|| self.table_box(scene.plan_nearest));
        let below = plan_nearest.as_ref().map_or(0, |b| b.height + gap);
        let poi = scene.poi.visible.then(|| TableBox { y: below, ..self.table_box(scene.poi) });
        let below = poi.as_ref().map_or(below, |b| b.y + b.height + gap);
        let carrier_table = scene.carrier_table.visible.then(|| TableBox { y: below, ..self.table_box(scene.carrier_table) });
        let tables_h = plan_nearest.iter().chain(&poi).chain(&carrier_table).map(|b| b.y + b.height).max().unwrap_or(0);
        let sheets_y = if tables_h > 0 && !scene.plan_sheets.is_empty() { tables_h + gap } else { tables_h };
        let (mut sheets, sheets_w, sheets_end) = self.sheet_boxes(scene.plan_sheets, sheets_y);
        let tables_w = plan_nearest.iter().chain(&poi).chain(&carrier_table).map(|b| b.width).max();
        if let Some(w) = tables_w {
            for (b, sheet) in sheets.iter_mut().zip(scene.plan_sheets) {
                let flex = sheet.right.iter().position(|r| !r).unwrap_or(0);
                let others: i32 = b.cols.iter().enumerate().filter(|(i, _)| *i != flex).map(|(_, c)| c).sum();
                b.cols[flex] = (w - others).max(MIN_FLEX_CHARS * self.fonts.row.char_w);
            }
        }
        let grids = sheets.iter().map(|b| b.cols.iter().sum::<i32>()).max().unwrap_or(0);
        let width = tables_w.map_or(sheets_w, |w| w.max(grids));
        let height = if sheets.is_empty() { tables_h } else { sheets_end - self.px(SHEET_GAP) };
        Layout {
            plan_nearest,
            poi,
            carrier_table,
            sheets,
            ..Layout::sized(width, height.max(1))
        }
    }

    fn layout_coords(&self, scene: &Scene) -> Layout {
        let (sheets, width, end) = self.sheet_boxes(scene.coord_sheets, 0);
        Layout {
            sheets,
            ..Layout::sized(width, (end - self.px(SHEET_GAP)).max(1))
        }
    }

    fn genus_parts<'a>(line: &'a BodyLine) -> Vec<(Option<&'a str>, &'a str)> {
        let mut parts: Vec<(Option<&str>, &str)> = line.genera.iter().map(|(g, t)| (Some(g.as_str()), t.as_str())).collect();
        if let Some(bio) = &line.bio {
            parts.push((None, bio.as_str()));
        }
        parts
    }

    fn layout_system(&self, scene: &Scene) -> Layout {
        let f = &self.fonts;
        let gap = NOTABLE_GAP * f.row.char_w;
        let list = scene.system_list.map(|l| {
            let row_h = Self::label_h(f.row) * SYSTEM_ROW_PCT / 100;
            let icon = Self::label_h(f.row) * HERE_ICON_PCT / 100;
            let icon_gap = icon * HERE_ICON_GAP_PCT / 100;
            let pad = self.px(JUMP_PAD);
            let widest = |text: &mut dyn Iterator<Item = &String>| text.map(|t| self.text_w(f.row, t)).max();
            let name_x = pad + icon + icon_gap;
            let name_w = widest(&mut l.lines.iter().map(|b| &b.name)).unwrap_or(0);
            let flag_x = name_x + name_w + 2 * gap;
            let flag_w = if l.lines.iter().any(|b| b.flag) { icon + 2 * gap } else { 0 };
            let parts: Vec<_> = l.lines.iter().flat_map(Self::genus_parts).collect();
            let mut keys: Vec<Option<&str>> = parts.iter().map(|(g, _)| *g).collect();
            keys.sort_by_key(|g| (g.map_or(GENUS_RGB.len() + 1, |g| GENUS_RGB.iter().position(|(n, _)| *n == g).unwrap_or(GENUS_RGB.len())), *g));
            keys.dedup();
            let mut x = flag_x + flag_w;
            let genus_cols = keys
                .into_iter()
                .map(|k| {
                    let at = x;
                    let w = parts.iter().filter(|(g, _)| *g == k).map(|(_, t)| self.text_w(f.row, t)).max().unwrap_or(0);
                    x += icon + icon_gap + w + 2 * gap;
                    (k.map(str::to_string), at)
                })
                .collect();
            let geo_x = x;
            let geo_w = widest(&mut l.lines.iter().filter_map(|b| b.geo.as_ref().map(|g| &g.0)));
            let value_x = geo_x + geo_w.map_or(0, |w| icon + icon_gap + w + 2 * gap);
            let value_w = widest(&mut l.lines.iter().map(|b| &b.value).chain(std::iter::once(&l.total))).unwrap_or(0);
            let title_h = Self::label_h(f.title);
            let title_w = pad + self.text_w(f.title, &l.title) + 2 * gap + self.text_w(f.title, &l.total);
            let width = (value_x + value_w).max(title_w) + pad;
            ListBox {
                row_h,
                icon,
                icon_gap,
                name_x,
                flag_x,
                genus_cols,
                geo_x,
                value_right: width - pad,
                width,
                height: title_h + row_h * l.lines.len() as i32,
            }
        });
        let below = list.as_ref().map_or(0, |b| b.height + self.px(SHEET_GAP));
        let (sheets, sheets_w, sheets_end) = self.sheet_boxes(scene.system_sheets, below);
        let width = list.as_ref().map_or(sheets_w, |b| b.width.max(sheets_w));
        let height = if sheets.is_empty() { below - self.px(SHEET_GAP) } else { sheets_end - self.px(SHEET_GAP) };
        Layout {
            system_list: list,
            sheets,
            ..Layout::sized(width, height.max(1))
        }
    }

    fn draw_system_list(&self, dc: HDC, b: &ListBox, list: &BodyList) {
        let f = &self.fonts;
        let pad = self.px(JUMP_PAD);
        let rows_h = b.row_h * list.lines.len() as i32;
        fill(dc, RECT { left: 0, top: rows_h, right: b.width, bottom: rows_h + 1 }, HEADER_LINE);
        text(dc, f.title, pad, rows_h + 1 + BD, &list.title, Role::Head.rgb());
        text(dc, f.title, b.value_right - self.text_w(f.title, &list.total), rows_h + 1 + BD, &list.total, Role::Head.rgb());
        let inset = (b.row_h - Self::label_h(f.row)) / 2;
        let mut icons = self.icons.borrow_mut();
        let size = b.icon as f64;
        let half = size / 2.0;
        for (i, line) in list.lines.iter().enumerate() {
            let y = i as i32 * b.row_h;
            let ty = y + inset + 1 + BD;
            let mid = (y + b.row_h / 2) as f64 + 0.5;
            let at = |x: i32| [x as f64 + half, mid];
            icons.extend(vector::body(at(pad), half, family_rgb(line.family), line.family == Family::Signal, false));
            outlined(dc, f.row, b.name_x, ty, &line.name, CLOCK_TEXT, CLOCK_EDGE);
            if line.flag {
                icons.extend(vector::flag(at(b.flag_x), size, CLOCK_TEXT, FIRST_FOOTFALL));
            }
            for (genus, t) in Self::genus_parts(line) {
                let Some(&(_, x)) = b.genus_cols.iter().find(|(k, _)| k.as_deref() == genus) else { continue };
                icons.push(match genus {
                    Some(g) => vector::genus(g, at(x), size, genus_rgb(g)),
                    None => vector::dna(at(x), size, EXO_DNA),
                });
                outlined(dc, f.row, x + b.icon + b.icon_gap, ty, t, CLOCK_TEXT, CLOCK_EDGE);
            }
            if let Some((geo, rgb)) = &line.geo {
                icons.extend(vector::volcano(at(b.geo_x), size, GEO_CONE, GEO_VOLCANO));
                outlined(dc, f.row, b.geo_x + b.icon + b.icon_gap, ty, geo, *rgb, CLOCK_EDGE);
            }
            if !line.value.is_empty() {
                outlined(dc, f.row, b.value_right - self.text_w(f.row, &line.value), ty, &line.value, CLOCK_TEXT, CLOCK_EDGE);
            }
        }
    }

    fn sheet_boxes(&self, list: &[Sheet], top: i32) -> (Vec<SheetBox>, i32, i32) {
        let f = &self.fonts;
        let pad = self.px(PAD_X / 2);
        let (title_h, head_h, row_h) = (Self::label_h(f.title), Self::label_h(f.head), Self::label_h(f.row));
        let mut y = top;
        let mut width = 1;
        let mut sheets = Vec::with_capacity(list.len());
        for sheet in list {
            let cols: Vec<i32> = sheet
                .heads
                .iter()
                .enumerate()
                .map(|(c, head)| {
                    let data = sheet.rows.iter().map(|(cells, _)| self.text_w(f.row, &cells[c])).max().unwrap_or(0);
                    data.max(self.text_w(f.head, head)) + 2 * pad + 2 * BD
                })
                .collect();
            width = width.max(cols.iter().sum::<i32>()).max(self.label_w(f.title, &sheet.title, 1));
            sheets.push(SheetBox { y, cols, title_h, head_h, row_h });
            y += title_h + head_h + row_h * sheet.rows.len() as i32 + self.px(SHEET_GAP);
        }
        (sheets, width, y)
    }

    fn layout_map(&self, scene: &Scene) -> Layout {
        let f = &self.fonts;
        let pad = self.px(PAD_X / 2);
        let cubes = || scene.sectors.iter().filter(|r| r.cube.is_some());
        let minimap = cubes().next().is_some().then(|| {
            let name_w = cubes().map(|r| self.text_w(f.row, r.system.as_deref().unwrap_or_default())).max().unwrap_or(0);
            let side = (name_w + 2 * pad + 2 * BD).max(3 * f.row.line_h + 2 * pad);
            let edge = side / MINIMAP_MARGIN_DIV;
            let fit = 3 * side + 1 + 2 * edge;
            let (w, h) = self.frame.map_or((fit, fit), |(.., w, h)| (w, h));
            MiniBox { side, gx: (w - 3 * side) / 2, gy: (h - 3 * side) / 2, w, h, edge }
        });
        let (width, height) = minimap.map_or((1, 1), |b| (b.w, b.h));
        Layout {
            minimap,
            ..Layout::sized(width, height)
        }
    }

    fn layout_marks(&self, scene: &Scene) -> Layout {
        let Some((bar, _, _)) = scene.marks else { return Layout::sized(1, 1) };
        let length = bar.length as f64;
        let at = |share: f64| (share * length).round() as i32;
        let (pad, half) = (at(FSS_MARK_SIDE), at(FSS_MARK_HALF));
        let row = bar.top - at(FSS_MARK_ABOVE);
        Layout {
            marks: Some(MarksBox { x: bar.left - pad, y: row - half, length, pad, row: half }),
            ..Layout::sized(bar.length + 2 * pad, 2 * half)
        }
    }

    fn draw_tips(&self, dc: HDC, b: &MarksBox, tips: &[Tip]) {
        let at = |share: f64| (share * b.length).round() as i32;
        let (r, y) = (at(FSS_TIP_R).max(1), 2 * b.row - at(FSS_TIP_INSET));
        for t in tips {
            dot(dc, POINT { x: b.pad + (t.at * b.length).round() as i32, y }, r, if t.up { FSS_TIP_UP } else { FSS_TIP_DOWN });
        }
    }

    fn draw_marks(&self, dc: HDC, b: &MarksBox, marks: &[Mark]) {
        let f = &self.fonts;
        let at = |share: f64| (share * b.length).round() as i32;
        let spread = 2 * at(FSS_ICON_RING_R);
        for (i, m) in marks.iter().enumerate() {
            let same: Vec<usize> = (0..marks.len()).filter(|&j| (marks[j].at - m.at).abs() < 1e-9).collect();
            let place = same.iter().position(|&j| j == i).unwrap_or(0) as i32;
            let x = b.pad + (m.at * b.length).round() as i32 + spread * (2 * place - (same.len() as i32 - 1)) / 2;
            match &m.class {
                Some(class) => {
                    let c = [x as f64 + 0.5, b.row as f64 + 0.5];
                    let family = bands::family(class);
                    let mut icons = self.icons.borrow_mut();
                    icons.extend(vector::body(c, b.length * FSS_ICON_RING_R, family_rgb(family), family == Family::Signal, m.atmosphere));
                }
                None => {
                    let warn = Role::Warn.rgb();
                    let side = at(FSS_WARN_SIDE);
                    let apex = POINT { x, y: b.row - side / 2 };
                    let (left, right) = (POINT { x: x - side / 2, y: b.row + side / 2 }, POINT { x: x + side / 2, y: b.row + side / 2 });
                    line(dc, apex, left, FSS_WARN_PEN, warn);
                    line(dc, left, right, FSS_WARN_PEN, warn);
                    line(dc, right, apex, FSS_WARN_PEN, warn);
                    text(dc, f.row, x - self.text_w(f.row, "!") / 2, b.row - f.row.line_h / 2 + side / 6, "!", warn);
                }
            }
        }
    }

    fn layout_popup(&self, scene: &Scene) -> Layout {
        let f = &self.fonts;
        let (title_h, row_h) = (Self::label_h(f.title), Self::label_h(f.row));
        let (name_w, star_w) = scene.popup.map_or((0, 0), |p| {
            p.rows.iter().fold((0, 0), |(n, s), (name, star, _)| {
                (n.max(self.text_w(f.row, name)), s.max(self.text_w(f.row, star)))
            })
        });
        let title_w = scene.popup.map_or(0, |p| self.text_w(f.title, &p.title));
        let rows = scene.popup.map_or(0, |p| p.rows.len() as i32);
        let width = (name_w + POPUP_GAP * f.row.char_w + star_w).max(title_w) + 2 * self.px(POPUP_PAD);
        let height = title_h + rows * row_h + self.px(POPUP_PAD);
        Layout {
            popup: Some(PopupBox { name_w, title_h, row_h }),
            ..Layout::sized(width, height)
        }
    }

    fn layout_left(&self, scene: &Scene) -> Layout {
        let sector = self.table_box(scene.sector);
        let (width, height) = (sector.width, sector.height + self.px(FOOTER_GAP));
        Layout {
            sector: Some(sector),
            ..Layout::sized(width, height)
        }
    }

    fn route_box(&self, p: &Panel, info: bool, x: i32, w: i32, beside_h: i32) -> RouteBox {
        let f = &self.fonts;
        let row_h = Self::label_h(f.row);
        let list_y = 1 + BD + Self::route_lines(p).len() as i32 * f.row.line_h + self.px(JUMP_GAP);
        let line = if jump::ahead(p).is_empty() { 0 } else { ROUTE_LINE_MIN_ROWS };
        let rows = line + i32::from(p.here.is_some()) + i32::from(info);
        RouteBox { x, w, list_y, row_h, info, height: beside_h.max(list_y + rows * row_h) }
    }

    fn here_in_route(scene: &Scene) -> bool {
        scene.jump.is_some_and(|p| p.here.is_some())
    }

    fn here_parts(scene: &Scene) -> Vec<HerePart> {
        let l = &scene.here_line;
        let mut parts = Vec::new();
        if !l.bodies.is_empty() {
            parts.push(HerePart::System(l.star_discovered.map(|d| if d { Role::Dim.rgb() } else { Role::Fg.rgb() })));
            parts.push(HerePart::Tinted(l.bodies.clone(), exobio::geo_rgb(l.bodies_new)));
        }
        if let Some(bio) = &l.bio {
            parts.push(HerePart::Dna);
            parts.push(HerePart::Text(bio.clone()));
        }
        for (genus, count, new) in &l.genera {
            parts.push(HerePart::Genus(genus.clone()));
            parts.push(HerePart::Tinted(count.clone(), exobio::geo_rgb(*new)));
        }
        if let Some(geo) = &l.geo {
            parts.push(HerePart::Volcano);
            parts.push(HerePart::Tinted(geo.clone(), exobio::geo_rgb(l.geo_new)));
        }
        for (family, count, unmapped) in &l.worlds {
            parts.push(HerePart::Family(*family));
            if !count.is_empty() {
                parts.push(HerePart::Tinted(count.clone(), exobio::geo_rgb(*unmapped)));
            }
        }
        if !l.rest.is_empty() {
            parts.push(HerePart::Text(l.rest.clone()));
        }
        if let Some(carriers) = &l.carriers {
            parts.push(HerePart::Carrier);
            parts.push(HerePart::Text(carriers.clone()));
        }
        parts
    }

    fn here_part_w(&self, part: &HerePart) -> i32 {
        let f = &self.fonts;
        match part {
            HerePart::Text(t) | HerePart::Tinted(t, _) => self.text_w(f.row, t),
            HerePart::Dna | HerePart::Genus(_) | HerePart::System(_) | HerePart::Volcano | HerePart::Carrier => {
                Self::label_h(f.row) * HERE_ICON_PCT / 100
            }
            HerePart::Family(_) => 2 * (Self::label_h(f.row) * NOTABLE_HALO_PCT / 100),
        }
    }

    fn here_info_w(&self, scene: &Scene) -> i32 {
        let gap = NOTABLE_GAP * self.fonts.row.char_w;
        let parts = Self::here_parts(scene);
        let after = |p: &HerePart| match p {
            HerePart::Text(_) | HerePart::Tinted(..) => gap,
            _ => self.here_part_w(p) * HERE_ICON_GAP_PCT / 100,
        };
        parts.iter().map(|p| self.here_part_w(p) + after(p)).sum::<i32>() - parts.last().map_or(0, &after)
    }

    fn here_info(&self, dc: HDC, x: i32, y: i32, max_w: i32, scene: &Scene, rgb: Option<Rgb>) {
        let f = &self.fonts;
        let gap = NOTABLE_GAP * f.row.char_w;
        let mid = y + Self::label_h(f.row) / 2;
        let mut at = x;
        for part in Self::here_parts(scene) {
            let w = self.here_part_w(&part);
            if at + w > x + max_w {
                break;
            }
            let centre = [(at + w / 2) as f64 + 0.5, mid as f64 + 0.5];
            match &part {
                HerePart::Text(t) => outlined(dc, f.row, at, y + 1 + BD, t, CLOCK_TEXT, CLOCK_EDGE),
                HerePart::Tinted(t, rgb) => outlined(dc, f.row, at, y + 1 + BD, t, *rgb, CLOCK_EDGE),
                HerePart::Dna => self.icons.borrow_mut().push(vector::dna(centre, w as f64, EXO_DNA)),
                HerePart::Genus(g) => self.icons.borrow_mut().push(vector::genus(g, centre, w as f64, genus_rgb(g))),
                HerePart::System(star) => system_icon(dc, POINT { x: at + w / 2, y: mid }, w, star.or(rgb).unwrap_or(CLOCK_TEXT)),
                HerePart::Volcano => self.icons.borrow_mut().extend(vector::volcano(centre, w as f64, GEO_CONE, GEO_VOLCANO)),
                HerePart::Carrier => carrier_icon(dc, at + w / 2, mid, w, JUMP_CARRIER),
                HerePart::Family(family) => {
                    self.icons.borrow_mut().extend(vector::body(centre, w as f64 / 2.0, family_rgb(*family), *family == Family::Signal, false))
                }
            }
            at += w + if matches!(part, HerePart::Text(_) | HerePart::Tinted(..)) { gap } else { w * HERE_ICON_GAP_PCT / 100 };
        }
    }

    fn clipped(&self, face: Face, s: &str, max_w: i32) -> String {
        if self.text_w(face, s) <= max_w {
            return s.to_string();
        }
        let chars: Vec<char> = s.chars().collect();
        (0..chars.len())
            .rev()
            .map(|n| format!("{}\u{2026}", chars[..n].iter().collect::<String>().trim_end()))
            .find(|t| self.text_w(face, t) <= max_w)
            .unwrap_or_default()
    }

    fn route_lines(p: &Panel) -> Vec<(String, Rgb)> {
        let mut lines = Vec::new();
        if !p.counts.is_empty() {
            lines.push((p.counts.clone(), Role::Dim.rgb()));
        }
        lines.extend(p.bio.iter().map(|(t, r)| (t.clone(), r.rgb())));
        lines
    }

    fn stop_name_x(&self) -> i32 {
        self.px(JUMP_PAD) + 2 * self.px(JUMP_TICK) + self.px(JUMP_PAD)
    }

    fn layout_top(&self, scene: &Scene) -> Layout {
        let f = &self.fonts;
        let table = self.table_box(scene.nearest);
        let half = table.width;
        let route_w = ROUTE_CHARS * f.row.char_w;
        let table_h = table.height;
        let nearest = scene.nearest.visible.then_some(table);
        let gap = TOP_TABLE_GAP * f.row.char_w;
        let width = half + gap + route_w;
        let info = Self::here_in_route(scene) && !scene.here_line.is_empty();
        let route = scene.jump.map(|p| self.route_box(p, info, half + gap, route_w, table_h));
        let top_h = table_h.max(route.as_ref().map_or(0, |r| r.height));
        let carrier_y = Some(top_h + self.px(FOOTER_GAP));
        let height = top_h + self.px(FOOTER_GAP) + Self::label_h(f.row);
        Layout {
            nearest,
            jump: route,
            carrier_y,
            ..Layout::sized(width, height)
        }
    }

    pub fn paint(&self, scene: &Scene) {
        unsafe {
            let mut ps = PAINTSTRUCT::default();
            BeginPaint(self.hwnd, &mut ps);
            let _ = EndPaint(self.hwnd, &ps);
        }
        self.render(scene);
    }

    fn render(&self, scene: &Scene) {
        let layout = self.layout(scene);
        let (w, h) = (layout.width.max(1), layout.height.max(1));
        unsafe {
            let screen = GetDC(None);
            let mem = CreateCompatibleDC(Some(screen));
            let info = BITMAPINFO {
                bmiHeader: BITMAPINFOHEADER {
                    biSize: std::mem::size_of::<BITMAPINFOHEADER>() as u32,
                    biWidth: w,
                    biHeight: -h,
                    biPlanes: 1,
                    biBitCount: 32,
                    biCompression: BI_RGB.0,
                    ..Default::default()
                },
                ..Default::default()
            };
            let mut bits: *mut core::ffi::c_void = std::ptr::null_mut();
            if let Ok(bmp) = CreateDIBSection(Some(mem), &info, DIB_RGB_COLORS, &mut bits, None, 0) {
                let old_bmp = SelectObject(mem, HGDIOBJ(bmp.0));
                fill(mem, RECT { left: 0, top: 0, right: w, bottom: h }, KEY);
                let _ = GdiFlush();
                let pixels = std::slice::from_raw_parts_mut(bits as *mut u32, (w * h) as usize);
                let backdrop = layout.minimap.map(|b| self.backdrop(b, scene.density)).filter(|b| b.pixels.len() == pixels.len());
                if let Some(b) = &backdrop {
                    for (p, (c, ..)) in pixels.iter_mut().zip(&b.pixels) {
                        *p = *c;
                    }
                }
                SetBkMode(mem, TRANSPARENT);
                self.icons.borrow_mut().clear();
                self.draw(mem, &layout, scene);
                let _ = GdiFlush();
                apply_alpha(pixels, self.opacity, backdrop.as_deref());
                for icon in self.icons.borrow().iter() {
                    icon.paint(pixels, w, h, self.opacity);
                }
                let size = SIZE { cx: w, cy: h };
                let origin = POINT::default();
                let blend = BLENDFUNCTION {
                    BlendOp: AC_SRC_OVER as u8,
                    BlendFlags: 0,
                    SourceConstantAlpha: 255,
                    AlphaFormat: AC_SRC_ALPHA as u8,
                };
                let _ = UpdateLayeredWindow(
                    self.hwnd,
                    Some(screen),
                    None,
                    Some(&size),
                    Some(mem),
                    Some(&origin),
                    COLORREF(0),
                    Some(&blend),
                    ULW_ALPHA,
                );
                SelectObject(mem, old_bmp);
                let _ = DeleteObject(HGDIOBJ(bmp.0));
            }
            let _ = DeleteDC(mem);
            ReleaseDC(None, screen);
        }
    }

    fn draw(&self, dc: HDC, l: &Layout, scene: &Scene) {
        let f = &self.fonts;
        if matches!(self.pane, Pane::Left | Pane::Plan | Pane::Top | Pane::System | Pane::Coords) {
            fill(dc, RECT { left: 0, top: 0, right: l.width, bottom: l.height }, PANEL_BG);
        }
        if let Some(b) = &l.nearest {
            self.draw_table(dc, b, scene.nearest, false);
        }
        if let Some(b) = &l.sector {
            self.draw_table(dc, b, scene.sector, true);
        }
        if let Some(b) = &l.plan_nearest {
            self.draw_table(dc, b, scene.plan_nearest, false);
        }
        if let Some(b) = &l.poi {
            self.draw_table(dc, b, scene.poi, false);
        }
        if let Some(b) = &l.carrier_table {
            self.draw_table(dc, b, scene.carrier_table, false);
        }
        if let (Some(b), Some(panel)) = (&l.jump, scene.jump) {
            self.draw_route(dc, b, panel, scene);
        }
        if let (Some(b), Some(p)) = (&l.popup, scene.popup) {
            self.draw_popup(dc, l.width, l.height, b, p);
        }
        if let (Some(b), Some((_, marks, tips))) = (&l.marks, scene.marks) {
            self.draw_marks(dc, b, marks);
            self.draw_tips(dc, b, tips);
        }
        if let Some(b) = l.minimap {
            self.draw_minimap(dc, b, scene);
        }
        if let (Some(b), Some(list)) = (&l.system_list, scene.system_list) {
            self.draw_system_list(dc, b, list);
        }
        let sheets = match self.pane {
            Pane::Plan => scene.plan_sheets,
            Pane::Coords => scene.coord_sheets,
            _ => scene.system_sheets,
        };
        for (b, sheet) in l.sheets.iter().zip(sheets) {
            self.draw_sheet(dc, b, sheet);
        }
        if let Some(cy) = l.carrier_y {
            let icon_w = f.row.line_h;
            let mid = cy + Self::label_h(f.row) / 2;
            let mut x = self.px(JUMP_PAD);
            if !scene.carrier.is_empty() {
                let rgb = scene.carrier_role.rgb();
                carrier_icon(dc, x + icon_w / 2, mid, f.row.line_h, rgb);
                x += icon_w + self.px(JUMP_PAD);
                text(dc, f.row, x, cy + 1 + BD, scene.carrier, rgb);
                x += self.text_w(f.row, scene.carrier) + 2 * f.row.char_w;
            }
            if let Some(plot) = scene.neutron_plot {
                let rgb = Role::Neutron.rgb();
                let centre = [(x + icon_w / 2) as f64, mid as f64];
                self.icons.borrow_mut().extend(vector::neutron(centre, icon_w as f64, NEUTRON_ICON_CORE, rgb));
                outlined(dc, f.row, x + icon_w + self.px(JUMP_PAD), cy + 1 + BD, plot, rgb, CLOCK_EDGE);
            }
        }
        if let (Pane::Top, Some(cy)) = (self.pane, l.carrier_y) {
            let cw = self.text_w(f.row, scene.clock);
            outlined(dc, f.row, l.width - self.px(JUMP_PAD) - cw, cy + 1 + BD, scene.clock, CLOCK_TEXT, CLOCK_EDGE);
            if !Self::here_in_route(scene) {
                let w = self.here_info_w(scene).min(l.width / 3);
                self.here_info(dc, (l.width - w) / 2, cy, l.width / 3, scene, None);
            }
        }
    }

    fn draw_route(&self, dc: HDC, b: &RouteBox, p: &Panel, scene: &Scene) {
        let f = &self.fonts;
        let cw = f.row.char_w;
        let (left, right) = (b.x + self.px(JUMP_PAD), b.x + b.w - self.px(JUMP_PAD));
        let mut y = 1 + BD;
        for (line, rgb) in Self::route_lines(p) {
            text(dc, f.row, left, y, &self.clipped(f.row, &line, right - left), rgb);
            y += f.row.line_h;
        }
        let lx = left + self.px(JUMP_TICK);
        let name_x = b.x + self.stop_name_x();
        let here_mid = b.list_y + b.row_h / 2;
        let ahead = jump::ahead(p);
        let Some(first) = ahead.first() else {
            if let Some(name) = &p.here {
                let top = here_mid - self.px(ROUTE_TICK_H) / 2;
                fill(dc, RECT { left: lx - self.px(ROUTE_TICK), top, right: lx + self.px(ROUTE_TICK) + 1, bottom: top + self.px(ROUTE_TICK_H) }, JUMP_CYAN);
                let star_x = name_x + self.text_w(f.row, name) + ROUTE_GAP_CHARS * cw;
                text(dc, f.row, name_x, b.list_y + 1 + BD, &self.clipped(f.row, name, right - name_x), JUMP_CYAN);
                text(dc, f.row, star_x, b.list_y + 1 + BD, &self.clipped(f.row, &p.here_star, right - star_x), p.here_rgb);
                if b.info {
                    self.here_info(dc, name_x, b.list_y + b.row_h, right - name_x, scene, Some(Role::Fg.rgb()));
                }
            }
            return;
        };
        let rest = &ahead[1..];
        let bottom = b.height - b.row_h / 2;
        let total: f64 = rest.iter().map(|l| l.ly).sum();
        let top = match &p.here {
            None => here_mid,
            Some(_) => here_mid + (1 + i32::from(b.info)) * b.row_h,
        };
        let stops: Vec<i32> = rest
            .iter()
            .scan(0.0, |run, leg| {
                *run += leg.ly;
                Some(top + if total > 0.0 { ((bottom - top) as f64 * *run / total).round() as i32 } else { 0 })
            })
            .collect();
        let bar = |from: i32, to: i32, rgb: Rgb| {
            fill(dc, RECT { left: lx - self.px(JUMP_BAR) / 2, top: from, right: lx - self.px(JUMP_BAR) / 2 + self.px(JUMP_BAR), bottom: to.max(from + 1) }, rgb);
        };
        let tick = |y: i32, scoopable: bool, rgb: Rgb| {
            let t = if scoopable { self.px(ROUTE_TICK) } else { self.px(ROUTE_TICK_SHORT) };
            let top = y - self.px(ROUTE_TICK_H) / 2;
            fill(dc, RECT { left: lx - t, top, right: lx + t + 1, bottom: top + self.px(ROUTE_TICK_H) }, rgb);
        };
        let ly_at = |row_y: i32, ly: f64| {
            let ly = light_years(ly);
            let x = right - self.text_w(f.row, &ly);
            text(dc, f.row, x, row_y, &ly, Role::Dim.rgb());
            x - ROUTE_GAP_CHARS * cw
        };
        if p.here.is_some() {
            let tip = top - self.px(ROUTE_TICK_H) / 2 - 1;
            let rgb = scene.hyper_glow.map_or(ROUTE_NEXT, |g| mix(ROUTE_NEXT, PANEL_BG, HYPER_REST * (1.0 - g)));
            bar(here_mid, tip - self.px(ROUTE_ARROW_H), rgb);
            arrow(dc, POINT { x: lx, y: tip }, self.px(ROUTE_ARROW_H), self.px(ROUTE_ARROW_HALF), rgb);
        }
        for (leg, (from, to)) in rest.iter().zip(std::iter::once(top).chain(stops.iter().copied()).zip(stops.iter().copied())) {
            bar(from, to, hop_colour(leg));
        }
        let icon_w = if p.carrier.is_some() { self.px(JUMP_PAD) + f.row.line_h } else { 0 };
        let star_x = name_x + jump::star_column(p, icon_w, |s| self.text_w(f.row, s)) + ROUTE_GAP_CHARS * cw;
        if let Some(name) = &p.here {
            tick(here_mid, true, JUMP_CYAN);
            let name = self.clipped(f.row, name, right - name_x);
            text(dc, f.row, name_x, b.list_y + 1 + BD, &name, JUMP_CYAN);
            text(dc, f.row, star_x, b.list_y + 1 + BD, &self.clipped(f.row, &p.here_star, right - star_x), p.here_rgb);
            if b.info {
                self.here_info(dc, name_x, b.list_y + b.row_h, right - name_x, scene, Some(Role::Fg.rgb()));
            }
        }
        tick(top, first.scoopable, ROUTE_NEXT);
        for (leg, y) in rest.iter().zip(&stops) {
            tick(*y, leg.scoopable, JUMP_ORANGE);
        }
        let row_y = top - b.row_h / 2 + 1 + BD;
        let end = if first.ly > 0.0 { ly_at(row_y, first.ly) } else { right };
        let next_name = self.clipped(f.row, &first.system, end - name_x - icon_w);
        let name_end = name_x + self.text_w(f.row, &next_name);
        text(dc, f.row, name_x, row_y, &next_name, ROUTE_NEXT);
        if let Some(open) = p.carrier {
            carrier_icon(dc, name_end + self.px(JUMP_PAD) + f.row.line_h / 2, top, f.row.line_h, if open { JUMP_CARRIER } else { JUMP_CARRIER_SHUT });
        }
        text(dc, f.row, star_x, row_y, &self.clipped(f.row, &p.star, end - star_x), p.class_rgb);
        if let Some((found, role)) = &p.discovery {
            text(dc, f.row, name_x, row_y + b.row_h, &self.clipped(f.row, found, right - name_x), role.rgb());
        }
        if let Some(last) = jump::destination(p) {
            let row_y = b.height - b.row_h + 1 + BD;
            let end = ly_at(row_y, jump::ahead_ly(p));
            text(dc, f.row, name_x, row_y, &self.clipped(f.row, &last.system, end - name_x), JUMP_ORANGE);
            text(dc, f.row, star_x, row_y, &self.clipped(f.row, &p.dest_star, end - star_x), p.dest_rgb);
        }
    }

    fn draw_popup(&self, dc: HDC, w: i32, h: i32, b: &PopupBox, p: &RoutePopup) {
        let f = &self.fonts;
        fill(dc, RECT { left: 0, top: 0, right: w, bottom: h }, HEADER_BG);
        fill(dc, RECT { left: 0, top: b.title_h - 1, right: w, bottom: b.title_h }, HEADER_LINE);
        text(dc, f.title, (w - self.text_w(f.title, &p.title)) / 2, 1 + BD, &p.title, HEADER_TEXT);
        let star_x = self.px(POPUP_PAD) + b.name_w + POPUP_GAP * f.row.char_w;
        for (r, (name, star, rgb)) in p.rows.iter().enumerate() {
            let y = b.title_h + r as i32 * b.row_h + 1 + BD;
            text(dc, f.row, self.px(POPUP_PAD), y, name, Role::Fg.rgb());
            text(dc, f.row, star_x, y, star, *rgb);
        }
    }

    fn draw_minimap(&self, dc: HDC, b: MiniBox, scene: &Scene) {
        let f = &self.fonts;
        let (side, line_h) = (b.side, f.row.line_h);
        for r in scene.sectors {
            let Some([dx, 0, dz]) = r.cube else { continue };
            let left = b.gx + (dx as i32 + 1) * side;
            let top = b.gy + (1 - dz as i32) * side;
            let corners = [
                POINT { x: left, y: top },
                POINT { x: left + side, y: top },
                POINT { x: left + side, y: top + side },
                POINT { x: left, y: top + side },
            ];
            for k in 0..4 {
                segment(dc, corners[k], corners[(k + 1) % 4], CUBE_LAYER);
            }
        }
        if let Some(d) = scene.density {
            self.draw_minimap_confirmed(dc, b, d.origin, scene.dots);
            unsafe {
                let _ = IntersectClipRect(dc, 0, 0, b.w, b.h);
            }
            self.draw_minimap_carrier(dc, b, d.origin, scene.carrier_path);
            self.draw_minimap_route(dc, b, d.origin, &scene.route);
            unsafe {
                let _ = SelectClipRgn(dc, None);
            }
        }
        for r in scene.sectors {
            let Some([dx, dy, dz]) = r.cube else { continue };
            let left = b.gx + (dx as i32 + 1) * side;
            let top = b.gy + (1 - dz as i32) * side;
            let name = r.system.as_deref().unwrap_or_default();
            let colour = if scene.lit == Some([dx, dy, dz]) {
                MINIMAP_NAME_LIT
            } else if dy != 0 || r.grp() == ROW_SECTOR_UNNAMED {
                MINIMAP_NAME_OFF
            } else if dx == 0 && dz == 0 {
                MINIMAP_NAME_HERE
            } else {
                MINIMAP_NAME
            };
            let x = left + (side - self.text_w(f.row, name)) / 2;
            let y = top + (side - 3 * line_h) / 2 + (1 - dy as i32) * line_h;
            text(dc, f.row, x, y, name, colour);
        }
        if let Some(d) = scene.density {
            let at = |p: [f64; 3]| Some(Self::minimap_point(b, d.origin, [p[0], p[2]])).filter(|&q| minimap_holds(b, q));
            unsafe {
                let _ = IntersectClipRect(dc, 0, 0, b.w, b.h);
            }
            if let Some(p) = scene.carrier_at.and_then(at) {
                carrier_icon(dc, p.x, p.y, line_h, scene.carrier_role.rgb());
            }
            if let Some(p) = scene.ship.and_then(at) {
                dot(dc, p, self.px(scene.ship_r), MINIMAP_SHIP);
            }
            unsafe {
                let _ = SelectClipRgn(dc, None);
            }
        }
    }

    fn minimap_point(b: MiniBox, origin: [f64; 2], p: [f64; 2]) -> POINT {
        let grid = 3 * b.side;
        POINT {
            x: b.gx + ((p[0] - origin[0]) / MINIMAP_BLOCK_LY * grid as f64).round() as i32,
            y: b.gy + grid - ((p[1] - origin[1]) / MINIMAP_BLOCK_LY * grid as f64).round() as i32,
        }
    }

    fn draw_minimap_confirmed(&self, dc: HDC, b: MiniBox, origin: [f64; 2], dots: &[(String, [f64; 3])]) {
        let prefs = prefs::get();
        for (kind, p) in dots.iter().filter(|(kind, _)| prefs.draws_on_map(kind)) {
            let POINT { x, y } = Self::minimap_point(b, origin, [p[0], p[2]]);
            if x < 0 || y < 0 || x + self.px(MINIMAP_DOT) > b.w || y + self.px(MINIMAP_DOT) > b.h {
                continue;
            }
            let c = kind_colour(kind).unwrap_or(Role::Head.rgb());
            fill(dc, RECT { left: x, top: y, right: x + self.px(MINIMAP_DOT), bottom: y + self.px(MINIMAP_DOT) }, c);
        }
    }

    fn draw_minimap_carrier(&self, dc: HDC, b: MiniBox, origin: [f64; 2], path: &[[f64; 3]]) {
        let at = |p: &[f64; 3]| Self::minimap_point(b, origin, [p[0], p[2]]);
        for ends in path.windows(2) {
            line(dc, at(&ends[0]), at(&ends[1]), self.px(MINIMAP_CARRIER_W), MINIMAP_CARRIER_ROUTE);
        }
        for stop in path {
            dot(dc, at(stop), self.px(MINIMAP_CARRIER_STOP_R), MINIMAP_CARRIER_ROUTE);
        }
    }

    fn draw_minimap_route(&self, dc: HDC, b: MiniBox, origin: [f64; 2], route: &MapRoute) {
        let at = |p: &[f64; 2]| Self::minimap_point(b, origin, *p);
        for (leg, ends) in route.legs.iter().zip(route.stops.windows(2)) {
            line(dc, at(&ends[0]), at(&ends[1]), self.px(MINIMAP_ROUTE_W), leg_colour(leg));
        }
        for (i, stop) in route.stops.iter().enumerate() {
            let behind = route.legs.get(i).is_some_and(|l| l.flown);
            dot(dc, at(stop), self.px(MINIMAP_STOP_R), if behind { JUMP_DIM } else { JUMP_ORANGE });
        }
    }

    fn backdrop(&self, b: MiniBox, density: Option<&MiniDensity>) -> Rc<Backdrop> {
        let at = density.map_or([0; 2], |d| [d.origin[0].to_bits(), d.origin[1].to_bits()]);
        let mut cache = self.backdrop.borrow_mut();
        if let Some((key, origin, made)) = cache.as_ref()
            && *key == b
            && *origin == at
        {
            return made.clone();
        }
        let made = Rc::new(Self::minimap_background(b, density));
        *cache = Some((b, at, made.clone()));
        made
    }

    fn minimap_background(b: MiniBox, density: Option<&MiniDensity>) -> Backdrop {
        let (w, h, side) = (b.w, b.h, b.side);
        let grid = 3 * side;
        let ly = MINIMAP_BLOCK_LY / grid as f64;
        let place = |i: i32| {
            let (x, y) = (i % w - b.gx, i / w - b.gy);
            (x, y, (x as f64 + 0.5) * ly, (grid - y) as f64 * ly - 0.5 * ly)
        };
        let glow: Vec<f64> = (0..w * h)
            .map(|i| {
                let (.., u, v) = place(i);
                (1.0 + density.map_or(0.0, |d| d.at(u, v))).ln()
            })
            .collect();
        let region: Vec<u8> = (0..w * h)
            .map(|i| {
                let (.., u, v) = place(i);
                density.map_or(0, |d| d.regions.at(d.origin[0] + u, d.origin[1] + v))
            })
            .collect();
        let mut sample: Vec<f64> = glow.iter().copied().step_by(MINIMAP_SAMPLE_STEP).collect();
        sample.sort_by(f64::total_cmp);
        let rank = |q: f64| sample.get(((sample.len() as f64 - 1.0) * q) as usize).copied().unwrap_or(0.0);
        let (lo, hi) = (rank(MINIMAP_STRETCH[0]), rank(MINIMAP_STRETCH[1]));
        let range = (hi - lo).max(f64::EPSILON);
        let edge = b.edge.max(1) as f64;
        let pixels = (0..w * h)
            .map(|i| {
                let (x, y, ..) = place(i);
                let (px, py) = (i % w, i / w);
                let id = region[i as usize];
                let border = (px + 1 < w && region[(i + 1) as usize] != id) || (py + 1 < h && region[(i + w) as usize] != id);
                let out_x = (b.edge - px).max(b.edge - (w - 1 - px)).max(0) as f64;
                let out_y = (b.edge - py).max(b.edge - (h - 1 - py)).max(0) as f64;
                let fade = (1.0 - out_x.hypot(out_y) / edge).clamp(0.0, 1.0);
                let fade = fade * fade * (3.0 - 2.0 * fade);
                if border {
                    return (dib_rgb(MINIMAP_REGION_BORDER), MINIMAP_REGION_ALPHA, fade);
                }
                let mut c = mix(MAP_SPACE, MAP_STARS, ((glow[i as usize] - lo) / range).clamp(0.0, 1.0).powf(1.4));
                if (side..2 * side).contains(&x) && (side..2 * side).contains(&y) {
                    c = mix(c, CUBE_FOOTPRINT, MINIMAP_HERE_TINT);
                }
                (dib_rgb(c), MINIMAP_ALPHA, fade)
            })
            .collect();
        Backdrop { pixels }
    }

    fn draw_sheet(&self, dc: HDC, b: &SheetBox, sheet: &Sheet) {
        let f = &self.fonts;
        let pad = self.px(PAD_X / 2);
        text(dc, f.title, 1 + BD, b.y + 1 + BD, &sheet.title, Role::Head.rgb());
        let xs: Vec<i32> = std::iter::once(0)
            .chain(b.cols.iter().scan(0, |acc, w| {
                *acc += w;
                Some(*acc)
            }))
            .collect();
        let head_y = b.y + b.title_h;
        let band = RECT { left: 0, top: head_y, right: xs[b.cols.len()], bottom: head_y + b.head_h };
        fill(dc, band, HEADER_BG);
        fill(dc, RECT { top: band.bottom - 1, ..band }, HEADER_LINE);
        let anchor = |c: usize| if sheet.right[c] { Anchor::E } else { Anchor::W };
        for (c, head) in sheet.heads.iter().enumerate() {
            place(dc, f.head, xs[c], xs[c + 1], head_y, head, anchor(c), pad, HEADER_TEXT);
        }
        for (r, (cells, _)) in sheet.rows.iter().enumerate() {
            let y = head_y + b.head_h + r as i32 * b.row_h;
            for (c, cell) in cells.iter().enumerate() {
                let fits = self.clipped(f.row, cell, xs[c + 1] - xs[c] - 2 * pad - 2 * BD);
                place(dc, f.row, xs[c], xs[c + 1], y, &fits, anchor(c), pad, sheet.rgb(r, c));
            }
        }
    }

    fn draw_table(&self, dc: HDC, b: &TableBox, t: &TargetTable, rules: bool) {
        let f = &self.fonts;
        let pad = self.px(PAD_X / 2);
        if let Some(title) = &t.title {
            text(dc, f.title, b.x + 1 + BD, b.y + 1 + BD, title, Role::Head.rgb());
        }
        let xs: Vec<i32> = std::iter::once(b.x)
            .chain(b.cols.iter().scan(b.x, |acc, w| {
                *acc += w;
                Some(*acc)
            }))
            .collect();
        let head_y = b.y + b.title_h;
        let band = RECT { left: b.x, top: head_y, right: xs[t.columns.len()], bottom: head_y + b.head_h };
        fill(dc, band, HEADER_BG);
        fill(dc, RECT { top: band.bottom - 1, ..band }, HEADER_LINE);
        for (c, col) in t.columns.iter().enumerate() {
            place(dc, f.head, xs[c], xs[c + 1], head_y, col.heading, col.anchor, pad, heading_colour(col));
        }
        let span = t.span();
        for (r, row) in t.draw_rows().into_iter().enumerate() {
            let y = head_y + b.head_h + r as i32 * b.row_h;
            let band = RECT { left: b.x, top: y, right: xs[t.columns.len()], bottom: y + b.row_h };
            if row.selected {
                fill(dc, band, SEL_BG);
            } else if row.plotted {
                fill(dc, band, PLOTTED_BG);
            }
            if row.plotted {
                fill(dc, RECT { right: b.x + self.px(PLOTTED_EDGE), ..band }, Role::Neutron.rgb());
            }
            if rules && r > 0 {
                for x in (b.x..xs[t.columns.len()]).step_by(TABLE_RULE_STEP as usize) {
                    unsafe {
                        let _ = SetPixelV(dc, x, y, colorref(TABLE_RULE));
                    }
                }
            }
            for (c, cell) in row.cells.iter().enumerate() {
                if cell.shown && !cell.text.is_empty() {
                    place(dc, f.row, xs[c], xs[c + 1], y, &cell.text, cell.anchor, pad, cell.fg);
                }
                if let Some(lead) = &cell.lead {
                    place(dc, f.row, xs[c], xs[c + 1], y, lead, Anchor::W, pad, cell.fg);
                }
            }
            if let (Some(w), Some((from, _))) = (&row.wide, span) {
                text(dc, f.row, xs[from] + pad + BD, y + 1 + BD, w, Role::Carrier.rgb());
            }
        }
    }

    pub fn mouse_down(&mut self) {
        if !self.draggable {
            return;
        }
        unsafe {
            let mut p = POINT::default();
            let mut r = RECT::default();
            if GetCursorPos(&mut p).is_ok() && GetWindowRect(self.hwnd, &mut r).is_ok() {
                self.drag = Some((p, r));
                SetCapture(self.hwnd);
            }
        }
    }

    pub fn mouse_move(&mut self) {
        self.track_drag();
    }

    fn track_drag(&mut self) {
        let Some((p0, r0)) = self.drag else { return };
        unsafe {
            if GetCapture() != self.hwnd {
                self.drag = None;
                return;
            }
            let mut p = POINT::default();
            if GetCursorPos(&mut p).is_ok() {
                let left = r0.left + p.x - p0.x;
                let _ = SetWindowPos(
                    self.hwnd,
                    None,
                    left,
                    r0.top + p.y - p0.y,
                    0,
                    0,
                    SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE,
                );
                if self.centre_x.is_some() {
                    self.centre_x = Some(left + (r0.right - r0.left) / 2);
                }
                if self.right_x.is_some() {
                    self.right_x = Some(left + (r0.right - r0.left));
                }
                if self.bottom_y.is_some() {
                    self.bottom_y = Some(r0.bottom + p.y - p0.y);
                }
            }
        }
    }

    pub fn mouse_up(&mut self) -> Option<(String, String)> {
        let (_, r0) = self.drag.take()?;
        let mut r = RECT::default();
        unsafe {
            let _ = ReleaseCapture();
            GetWindowRect(self.hwnd, &mut r).ok()?;
        }
        if (r.left, r.top) == (r0.left, r0.top) {
            return None;
        }
        let x = self.centre_x.or(self.right_x).unwrap_or(r.left);
        let y = self.bottom_y.unwrap_or(r.top);
        Some(prefs::set_place(&self.pane.name(), (x, y)))
    }

    pub fn default_proc(hwnd: HWND, msg: u32, wparam: WPARAM, lparam: LPARAM) -> LRESULT {
        unsafe { DefWindowProcW(hwnd, msg, wparam, lparam) }
    }
}

fn fill(dc: HDC, r: RECT, c: Rgb) {
    unsafe {
        let brush = CreateSolidBrush(colorref(c));
        FillRect(dc, &r, brush);
        let _ = DeleteObject(HGDIOBJ(brush.0));
    }
}

fn line(dc: HDC, a: POINT, b: POINT, width: i32, c: Rgb) {
    unsafe {
        let pen = CreatePen(PS_SOLID, width, colorref(c));
        let old = SelectObject(dc, HGDIOBJ(pen.0));
        let _ = MoveToEx(dc, a.x, a.y, None);
        let _ = LineTo(dc, b.x, b.y);
        SelectObject(dc, old);
        let _ = DeleteObject(HGDIOBJ(pen.0));
    }
}

fn family_rgb(family: Family) -> Rgb {
    match family {
        Family::Asteroid => FSS_ICON_ASTEROID,
        Family::Rock => FSS_ICON_ROCK,
        Family::Signal | Family::Ice => FSS_ICON_ICE,
        Family::EarthLike => FSS_ICON_EARTH,
        Family::Ammonia => FSS_ICON_AMMONIA,
        Family::Water => FSS_ICON_WATER,
        Family::Gas => FSS_ICON_GAS,
    }
}

fn ring(dc: HDC, at: POINT, r: i32, width: i32, c: Rgb) {
    unsafe {
        let pen = CreatePen(PS_SOLID, width, colorref(c));
        let old_brush = SelectObject(dc, GetStockObject(NULL_BRUSH));
        let old_pen = SelectObject(dc, HGDIOBJ(pen.0));
        let _ = Ellipse(dc, at.x - r, at.y - r, at.x + r + 1, at.y + r + 1);
        SelectObject(dc, old_pen);
        SelectObject(dc, old_brush);
        let _ = DeleteObject(HGDIOBJ(pen.0));
    }
}

fn dot(dc: HDC, at: POINT, r: i32, c: Rgb) {
    unsafe {
        let brush = CreateSolidBrush(colorref(c));
        let pen = CreatePen(PS_SOLID, 1, colorref(c));
        let old_brush = SelectObject(dc, HGDIOBJ(brush.0));
        let old_pen = SelectObject(dc, HGDIOBJ(pen.0));
        let _ = Ellipse(dc, at.x - r, at.y - r, at.x + r + 1, at.y + r + 1);
        SelectObject(dc, old_pen);
        SelectObject(dc, old_brush);
        let _ = DeleteObject(HGDIOBJ(pen.0));
        let _ = DeleteObject(HGDIOBJ(brush.0));
    }
}

enum HerePart {
    Text(String),
    Tinted(String, Rgb),
    System(Option<Rgb>),
    Dna,
    Genus(String),
    Volcano,
    Carrier,
    Family(Family),
}

fn system_icon(dc: HDC, centre: POINT, size: i32, c: Rgb) {
    let outer = size / 2 - 1;
    let inner = outer * 11 / 20;
    let pen = (size / 14).max(1);
    ring(dc, centre, outer, pen, c);
    ring(dc, centre, inner, pen, c);
    dot(dc, centre, (outer / 4).max(1), c);
    let planet = (outer / 6).max(1);
    for (r, deg) in [(inner, 80.0_f64), (inner, 260.0), (outer, 40.0), (outer, 220.0)] {
        let a = deg.to_radians();
        dot(dc, POINT { x: centre.x + (r as f64 * a.cos()).round() as i32, y: centre.y - (r as f64 * a.sin()).round() as i32 }, planet, c);
    }
}

fn arrow(dc: HDC, tip: POINT, h: i32, half: i32, c: Rgb) {
    polygon(dc, &[tip, POINT { x: tip.x - half, y: tip.y - h }, POINT { x: tip.x + half, y: tip.y - h }], c);
}

fn polygon(dc: HDC, corners: &[POINT], c: Rgb) {
    unsafe {
        let brush = CreateSolidBrush(colorref(c));
        let pen = CreatePen(PS_SOLID, 1, colorref(c));
        let old_brush = SelectObject(dc, HGDIOBJ(brush.0));
        let old_pen = SelectObject(dc, HGDIOBJ(pen.0));
        let _ = Polygon(dc, corners);
        SelectObject(dc, old_pen);
        SelectObject(dc, old_brush);
        let _ = DeleteObject(HGDIOBJ(pen.0));
        let _ = DeleteObject(HGDIOBJ(brush.0));
    }
}

fn segment(dc: HDC, a: POINT, b: POINT, c: Rgb) {
    unsafe {
        let pen = CreatePen(PS_SOLID, 1, colorref(c));
        let old = SelectObject(dc, HGDIOBJ(pen.0));
        let _ = MoveToEx(dc, a.x, a.y, None);
        let _ = LineTo(dc, b.x, b.y);
        SelectObject(dc, old);
        let _ = DeleteObject(HGDIOBJ(pen.0));
    }
}

fn hop_colour(leg: &jump::Leg) -> Rgb {
    match (leg.flown, leg.boosted) {
        (true, true) => JUMP_TEAL_DIM,
        (false, true) => JUMP_TEAL,
        (true, false) => JUMP_DIM,
        (false, false) => JUMP_ORANGE,
    }
}

fn leg_colour(leg: &jump::Leg) -> Rgb {
    if leg.next { JUMP_CYAN } else { hop_colour(leg) }
}

fn minimap_holds(b: MiniBox, p: POINT) -> bool {
    (0..b.w).contains(&p.x) && (0..b.h).contains(&p.y)
}

pub fn pulse_radius(ms: u64) -> i32 {
    let (lo, hi) = MINIMAP_SHIP_R;
    let phase = (ms % MINIMAP_SHIP_PULSE_MS) as f64 / MINIMAP_SHIP_PULSE_MS as f64;
    let swell = (1.0 - (phase * std::f64::consts::TAU).cos()) / 2.0;
    (lo as f64 + (hi - lo) as f64 * swell).round() as i32
}

pub fn standby_glow(ms: u64) -> f64 {
    let phase = (ms % HYPER_PULSE_MS) as f64 / HYPER_PULSE_MS as f64;
    (1.0 - (phase * std::f64::consts::TAU).cos()) / 2.0
}

fn carrier_icon(dc: HDC, cx: i32, cy: i32, h: i32, c: Rgb) {
    let unit = h as f64 / CARRIER_ICON_SPAN;
    let at = |(x, y): (f64, f64)| POINT { x: cx + (x * unit).round() as i32, y: cy + (y * unit).round() as i32 };
    let pen = (h / CARRIER_ICON_PEN_DIV).max(1);
    for k in 0..CARRIER_ICON_HULL.len() {
        line(dc, at(CARRIER_ICON_HULL[k]), at(CARRIER_ICON_HULL[(k + 1) % CARRIER_ICON_HULL.len()]), pen, c);
    }
    let (ox, oy, r) = CARRIER_ICON_RING;
    let ring: Vec<POINT> = (0..=CARRIER_ICON_RING_STEPS)
        .map(|k| {
            let t = k as f64 * std::f64::consts::TAU / CARRIER_ICON_RING_STEPS as f64;
            at((ox + r * t.cos(), oy + r * t.sin()))
        })
        .collect();
    for w in ring.windows(2) {
        line(dc, w[0], w[1], pen, c);
    }
    let bar = CARRIER_ICON_BAR;
    line(dc, at((ox - bar, oy)), at((ox + bar, oy)), pen, c);
}

fn outlined(dc: HDC, face: Face, x: i32, y: i32, s: &str, c: Rgb, edge: Rgb) {
    for (dx, dy) in [(-1, -1), (0, -1), (1, -1), (-1, 0), (1, 0), (-1, 1), (0, 1), (1, 1)] {
        text(dc, face, x + dx, y + dy, s, edge);
    }
    text(dc, face, x, y, s, c);
}

fn text(dc: HDC, face: Face, x: i32, y: i32, s: &str, c: Rgb) {
    unsafe {
        let old = SelectObject(dc, HGDIOBJ(face.font.0));
        SetTextColor(dc, colorref(c));
        let _ = TextOutW(dc, x, y, &wide(s));
        SelectObject(dc, old);
    }
}

#[allow(clippy::too_many_arguments)]
fn place(dc: HDC, face: Face, left: i32, right: i32, y: i32, s: &str, anchor: Anchor, pad: i32, c: Rgb) {
    unsafe {
        let old = SelectObject(dc, HGDIOBJ(face.font.0));
        let w = wide(s);
        let mut size = SIZE::default();
        let _ = GetTextExtentPoint32W(dc, &w, &mut size);
        let x = match anchor {
            Anchor::W => left + pad + BD,
            Anchor::E => right - pad - BD - size.cx,
        };
        SetTextColor(dc, colorref(c));
        let _ = TextOutW(dc, x, y + 1 + BD, &w);
        SelectObject(dc, old);
    }
}

fn delete_fonts(f: &Fonts) {
    for face in [f.row, f.head, f.small, f.title] {
        unsafe {
            let _ = DeleteObject(HGDIOBJ(face.font.0));
        }
    }
}

fn make_fonts(hwnd: HWND, base: i32, scale: f64) -> Fonts {
    let face = |pt: i32, bold: bool| unsafe {
        let family: Vec<u16> = FONT_FAMILY.encode_utf16().chain(std::iter::once(0)).collect();
        let font = CreateFontW(
            -((pt as f64 * scale * 96.0 / 72.0).round() as i32),
            0,
            0,
            0,
            if bold { FW_BOLD.0 as i32 } else { FW_NORMAL.0 as i32 },
            0,
            0,
            0,
            DEFAULT_CHARSET,
            OUT_DEFAULT_PRECIS,
            CLIP_DEFAULT_PRECIS,
            DEFAULT_QUALITY,
            (FIXED_PITCH.0 | FF_MODERN.0) as u32,
            PCWSTR(family.as_ptr()),
        );
        let dc = GetDC(Some(hwnd));
        let old = SelectObject(dc, HGDIOBJ(font.0));
        let mut tm = TEXTMETRICW::default();
        let _ = GetTextMetricsW(dc, &mut tm);
        let mut zero = SIZE::default();
        let _ = GetTextExtentPoint32W(dc, &wide("0"), &mut zero);
        SelectObject(dc, old);
        ReleaseDC(Some(hwnd), dc);
        Face { font, char_w: zero.cx, line_h: tm.tmAscent + tm.tmDescent }
    };
    Fonts {
        row: face(base, false),
        head: face(base, true),
        small: face((base - 2).max(7), false),
        title: face((base - 1).max(8), true),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    const BOX: MiniBox = MiniBox { side: 100, gx: 50, gy: 50, w: 400, h: 400, edge: 33 };

    #[test]
    fn the_hyperspace_arrow_glows_up_and_down_once_a_period() {
        assert_eq!(standby_glow(0), 0.0);
        assert!((standby_glow(HYPER_PULSE_MS / 2) - 1.0).abs() < 1e-9);
        assert!(standby_glow(HYPER_PULSE_MS / 4) < standby_glow(HYPER_PULSE_MS / 3));
        assert_eq!(standby_glow(HYPER_PULSE_MS * 3 + 250), standby_glow(250));
        assert!((0..HYPER_PULSE_MS).map(standby_glow).all(|g| (0.0..=1.0).contains(&g)));
    }

    #[test]
    fn the_ship_pulses_between_its_radii_once_a_period() {
        let (lo, hi) = MINIMAP_SHIP_R;
        assert_eq!(pulse_radius(0), lo);
        assert_eq!(pulse_radius(MINIMAP_SHIP_PULSE_MS / 2), hi);
        assert_eq!(pulse_radius(MINIMAP_SHIP_PULSE_MS), lo);
        assert_eq!(pulse_radius(7 * MINIMAP_SHIP_PULSE_MS + 300), pulse_radius(300));
        assert!((0..MINIMAP_SHIP_PULSE_MS).map(pulse_radius).all(|r| (lo..=hi).contains(&r)));
    }

    #[test]
    fn a_position_projects_north_up_from_the_block_corner() {
        let origin = [1000.0, -2000.0];
        let corner = Overlay::minimap_point(BOX, origin, origin);
        assert_eq!((corner.x, corner.y), (50, 350));
        let far = Overlay::minimap_point(BOX, origin, [origin[0] + MINIMAP_BLOCK_LY, origin[1] + MINIMAP_BLOCK_LY]);
        assert_eq!((far.x, far.y), (350, 50));
    }

    #[test]
    fn a_position_off_the_pane_is_not_drawn() {
        assert!(minimap_holds(BOX, POINT { x: 0, y: 0 }));
        assert!(minimap_holds(BOX, POINT { x: 399, y: 399 }));
        assert!(!minimap_holds(BOX, POINT { x: 400, y: 10 }));
        assert!(!minimap_holds(BOX, POINT { x: 10, y: -1 }));
        let beyond = Overlay::minimap_point(BOX, [0.0, 0.0], [-MINIMAP_BLOCK_LY, 0.0]);
        assert!(!minimap_holds(BOX, beyond));
    }
}
