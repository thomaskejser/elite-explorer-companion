use std::cell::RefCell;
use std::rc::Rc;

use windows::Win32::Foundation::{COLORREF, HWND, LPARAM, LRESULT, POINT, RECT, SIZE, WPARAM};
use windows::Win32::Graphics::Gdi::{
    AC_SRC_ALPHA, AC_SRC_OVER, BI_RGB, CreatePen, Ellipse, IntersectClipRect, SelectClipRgn, LineTo, MoveToEx, PS_SOLID, BITMAPINFO, BITMAPINFOHEADER, BLENDFUNCTION, BeginPaint, CLIP_DEFAULT_PRECIS,
    CreateCompatibleDC, CreateDIBSection, CreateFontW, CreateSolidBrush, DEFAULT_CHARSET, DEFAULT_QUALITY,
    DIB_RGB_COLORS, DeleteDC, DeleteObject, EndPaint, FF_MODERN, FIXED_PITCH, FW_BOLD, FW_NORMAL, FillRect, GdiFlush,
    GetDC, GetTextExtentPoint32W, GetTextMetricsW, HDC, HFONT, HGDIOBJ, OUT_DEFAULT_PRECIS, PAINTSTRUCT, ReleaseDC,
    SelectObject, SetBkMode, SetPixelV, SetTextColor, TEXTMETRICW, TRANSPARENT, TextOutW,
};
use windows::Win32::System::LibraryLoader::GetModuleHandleW;
use windows::Win32::UI::HiDpi::GetDpiForWindow;
use windows::Win32::UI::WindowsAndMessaging::{GetSystemMetrics, SM_CXSCREEN, SM_CYSCREEN};
use windows::Win32::Graphics::Gdi::{GetMonitorInfoW, MONITOR_DEFAULTTOPRIMARY, MONITORINFO, MonitorFromWindow};
use windows::Win32::UI::Input::KeyboardAndMouse::{GetCapture, ReleaseCapture, SetCapture};
use windows::Win32::UI::WindowsAndMessaging::{
    CS_HREDRAW, CS_VREDRAW, CreateWindowExW, DefWindowProcW, GetCursorPos, GetWindowRect, HWND_TOPMOST,
    IDC_ARROW, LoadCursorW, RegisterClassExW, SW_HIDE, SW_SHOWNOACTIVATE, SWP_NOACTIVATE, SWP_NOMOVE, SWP_NOSIZE,
    SWP_NOZORDER, SetTimer, SetWindowPos, ShowWindow, ULW_ALPHA, UpdateLayeredWindow, WNDCLASSEXW, WS_EX_LAYERED,
    WS_EX_NOACTIVATE, WS_EX_TOOLWINDOW, WS_EX_TOPMOST, WS_POPUP,
};
use windows::core::{PCWSTR, w};

use crate::database::{MINIMAP_BLOCK_LY, MiniDensity};
use crate::exobio::Sheet;
use crate::jump::{self, MapRoute, Panel, RoutePopup};
use crate::row::{ROW_SECTOR_UNNAMED, Row};
use crate::table::{TargetTable, light_years};
use crate::theme::*;

pub const TICK_TIMER: usize = 1;
pub const FLASH_TIMER: usize = 2;

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
    Right,
    Popup,
    Map,
    Plan,
}

pub struct Scene<'a> {
    pub nearest: &'a TargetTable,
    pub sector: &'a TargetTable,
    pub poi: &'a TargetTable,
    pub carrier_table: &'a TargetTable,
    pub clock: &'a str,
    pub carrier: &'a str,
    pub carrier_role: Role,
    pub here_bodies: String,
    pub jump: Option<&'a Panel>,
    pub exobio: &'a [Sheet],
    pub popup: Option<&'a RoutePopup>,
    pub sectors: &'a [Row],
    pub density: Option<&'a MiniDensity>,
    pub route: MapRoute,
    pub lit: Option<[i64; 3]>,
    pub dots: &'a [(String, [f64; 3])],
    pub carrier_path: &'a [[f64; 3]],
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
    jump: Option<RouteBox>,
    sheets: Vec<SheetBox>,
    footer_y: i32,
    carrier_y: Option<i32>,
    popup: Option<PopupBox>,
    minimap: Option<MiniBox>,
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
            jump: None,
            sheets: Vec::new(),
            footer_y: height,
            carrier_y: None,
            popup: None,
            minimap: None,
        }
    }
}

struct RouteBox {
    x: i32,
    w: i32,
    list_y: i32,
    row_h: i32,
    height: i32,
}

struct PopupBox {
    name_w: i32,
    title_h: i32,
    row_h: i32,
}

pub struct Overlay {
    pub hwnd: HWND,
    pane: Pane,
    centre_x: Option<i32>,
    right_x: Option<i32>,
    bottom_y: Option<i32>,
    frame: Option<(i32, i32, i32, i32)>,
    backdrop: RefCell<Option<BackdropCache>>,
    fonts: Fonts,
    base_pt: i32,
    pub chrome: bool,
    draggable: bool,
    shown: bool,
    status: String,
    footer: (String, Role),
    size: (i32, i32),
    drag: Option<(POINT, RECT)>,
    opacity: u8,
}

impl Overlay {
    pub fn create(
        font_pt: i32,
        opacity: f64,
        pos: (Option<i32>, Option<i32>),
        draggable: bool,
        chrome: bool,
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
            let fonts = make_fonts(hwnd, font_pt);
            let scale = |v: i32| v * GetDpiForWindow(hwnd) as i32 / 96;
            let centre_x = (pane == Pane::Top).then(|| pos.0.unwrap_or_else(|| GetSystemMetrics(SM_CXSCREEN) / 2));
            let right_x = matches!(pane, Pane::Right | Pane::Plan).then(|| GetSystemMetrics(SM_CXSCREEN) - scale(EDGE_MARGIN));
            let bottom_y = (pane == Pane::Left && pos.1.is_none()).then(|| GetSystemMetrics(SM_CYSCREEN) - scale(EDGE_MARGIN));
            let x = centre_x.or(right_x).unwrap_or_else(|| pos.0.unwrap_or_else(|| scale(EDGE_MARGIN)));
            let y = pos.1.unwrap_or_else(|| scale(EDGE_MARGIN));
            let _ = SetWindowPos(hwnd, Some(HWND_TOPMOST), x, y, 0, 0, SWP_NOSIZE | SWP_NOACTIVATE);
            Ok(Overlay {
                hwnd,
                pane,
                centre_x,
                right_x,
                bottom_y,
                frame: None,
                backdrop: RefCell::new(None),
                fonts,
                base_pt: font_pt,
                chrome,
                draggable,
                shown: false,
                status: String::new(),
                footer: (String::new(), Role::Dim),
                size: (0, 0),
                drag: None,
                opacity: (opacity.clamp(0.0, 1.0) * 255.0).round() as u8,
            })
        }
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

    pub fn dpi_changed(&mut self) {
        self.fonts = make_fonts(self.hwnd, self.base_pt);
        self.size = (0, 0);
    }

    pub fn set_status(&mut self, text: String) {
        if self.chrome && self.pane == Pane::Left {
            self.status = text;
        }
    }

    pub fn set_footer(&mut self, text: &str, role: Role) {
        if self.chrome && self.pane == Pane::Left {
            self.footer = (text.to_string(), role);
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

    pub fn fit_above(&mut self, below: &Overlay) {
        unsafe {
            let mut r = RECT::default();
            let _ = GetWindowRect(below.hwnd, &mut r);
            let mut screen = MONITORINFO { cbSize: std::mem::size_of::<MONITORINFO>() as u32, ..Default::default() };
            let _ = GetMonitorInfoW(MonitorFromWindow(below.hwnd, MONITOR_DEFAULTTOPRIMARY), &mut screen);
            let gap = EDGE_MARGIN * GetDpiForWindow(self.hwnd) as i32 / 96;
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
        let pad = PAD_X / 2;
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
            Pane::Right => self.layout_right(scene),
            Pane::Popup => self.layout_popup(scene),
            Pane::Map => self.layout_map(scene),
            Pane::Plan => self.layout_plan(scene),
        }
    }

    fn layout_plan(&self, scene: &Scene) -> Layout {
        let poi = scene.poi.visible.then(|| self.table_box(scene.poi));
        let below = poi.as_ref().map_or(0, |b| b.height + TOP_TABLE_GAP * self.fonts.row.char_w);
        let carrier_table = scene.carrier_table.visible.then(|| TableBox { y: below, ..self.table_box(scene.carrier_table) });
        let width = poi.iter().chain(&carrier_table).map(|b| b.width).max().unwrap_or(1);
        let height = carrier_table.as_ref().map_or(poi.as_ref().map_or(1, |b| b.height), |b| b.y + b.height);
        Layout {
            poi,
            carrier_table,
            ..Layout::sized(width, height)
        }
    }

    fn layout_right(&self, scene: &Scene) -> Layout {
        let f = &self.fonts;
        let pad = PAD_X / 2;
        let (title_h, head_h, row_h) = (Self::label_h(f.title), Self::label_h(f.head), Self::label_h(f.row));
        let mut y = 0;
        let mut width = 1;
        let mut sheets = Vec::with_capacity(scene.exobio.len());
        for sheet in scene.exobio {
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
            y += title_h + head_h + row_h * sheet.rows.len() as i32 + SHEET_GAP;
        }
        Layout {
            sheets,
            ..Layout::sized(width, y.max(1))
        }
    }

    fn layout_map(&self, scene: &Scene) -> Layout {
        let f = &self.fonts;
        let pad = PAD_X / 2;
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
        let width = (name_w + POPUP_GAP * f.row.char_w + star_w).max(title_w) + 2 * POPUP_PAD;
        let height = title_h + rows * row_h + POPUP_PAD;
        Layout {
            popup: Some(PopupBox { name_w, title_h, row_h }),
            ..Layout::sized(width, height)
        }
    }

    fn layout_left(&self, scene: &Scene) -> Layout {
        let f = &self.fonts;
        let chrome_h = if self.chrome { Self::label_h(f.title).max(Self::label_h(f.small)) } else { 0 };
        let mut sector = self.table_box(scene.sector);
        let mut width = sector.width;
        if self.chrome {
            let bar = self.label_w(f.title, "::: sector rares :::", 1) + self.label_w(f.small, &self.status, 1) + 10;
            width = width.max(bar);
        }
        sector.y = chrome_h;
        let footer_y = sector.y + sector.height + FOOTER_GAP;
        let footer_h = if self.chrome { Self::label_h(f.small) } else { 0 };
        Layout {
            sector: Some(sector),
            footer_y,
            ..Layout::sized(width, footer_y + footer_h)
        }
    }

    fn route_box(&self, p: &Panel, x: i32, w: i32, beside_h: i32) -> RouteBox {
        let f = &self.fonts;
        let row_h = Self::label_h(f.row);
        let list_y = 1 + BD + Self::route_lines(p).len() as i32 * f.row.line_h + JUMP_GAP;
        let rows = ROUTE_LINE_MIN_ROWS + i32::from(p.here.is_some());
        RouteBox { x, w, list_y, row_h, height: beside_h.max(list_y + rows * row_h) }
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

    fn stop_name_x() -> i32 {
        JUMP_PAD + 2 * JUMP_TICK + JUMP_PAD
    }

    fn layout_top(&self, scene: &Scene) -> Layout {
        let f = &self.fonts;
        let table = self.table_box(scene.nearest);
        let half = table.width;
        let route_w = ROUTE_CHARS * f.row.char_w;
        let nearest = scene.nearest.visible.then_some(table);
        let gap = TOP_TABLE_GAP * f.row.char_w;
        let width = half + gap + route_w;
        let route = scene.jump.map(|p| self.route_box(p, half + gap, route_w, nearest.as_ref().map_or(0, |b| b.height)));
        let top_h = nearest.as_ref().map_or(0, |b| b.height).max(route.as_ref().map_or(0, |r| r.height));
        let carrier_y = Some(top_h + FOOTER_GAP);
        let height = top_h + FOOTER_GAP + Self::label_h(f.row);
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
                self.draw(mem, &layout, scene);
                let _ = GdiFlush();
                apply_alpha(pixels, self.opacity, backdrop.as_deref());
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
        if matches!(self.pane, Pane::Left | Pane::Plan | Pane::Top) {
            fill(dc, RECT { left: 0, top: 0, right: l.width, bottom: l.height }, PANEL_BG);
        }
        if self.chrome && self.pane == Pane::Left {
            text(dc, f.title, 1 + BD, 1 + BD, "::: Explorers Companion :::", Role::Head.rgb());
            let sw = self.text_w(f.small, &self.status);
            text(dc, f.small, l.width - 2 - BD - 1 - sw, 1 + BD, &self.status, Role::Dim.rgb());
        }
        if let Some(b) = &l.nearest {
            self.draw_table(dc, b, scene.nearest, false);
        }
        if let Some(b) = &l.sector {
            self.draw_table(dc, b, scene.sector, true);
        }
        if let Some(b) = &l.poi {
            self.draw_table(dc, b, scene.poi, false);
        }
        if let Some(b) = &l.carrier_table {
            self.draw_table(dc, b, scene.carrier_table, false);
        }
        if let (Some(b), Some(panel)) = (&l.jump, scene.jump) {
            self.draw_route(dc, b, panel);
        }
        if let (Some(b), Some(p)) = (&l.popup, scene.popup) {
            self.draw_popup(dc, l.width, l.height, b, p);
        }
        if let Some(b) = l.minimap {
            self.draw_minimap(dc, b, scene);
        }
        for (b, sheet) in l.sheets.iter().zip(scene.exobio) {
            self.draw_sheet(dc, b, sheet);
        }
        if let Some(cy) = l.carrier_y
            && !scene.carrier.is_empty()
        {
            let state = scene.carrier;
            let icon_w = f.row.line_h;
            let x = (l.width - icon_w - JUMP_PAD - self.text_w(f.row, state)) / 2;
            let rgb = scene.carrier_role.rgb();
            carrier_icon(dc, x + icon_w / 2, cy + Self::label_h(f.row) / 2, f.row.line_h, rgb);
            text(dc, f.row, x + icon_w + JUMP_PAD, cy + 1 + BD, state, rgb);
        }
        if self.chrome && self.pane == Pane::Left && !self.footer.0.is_empty() {
            text(dc, f.small, 1 + BD, l.footer_y + 1 + BD, &self.footer.0, self.footer.1.rgb());
        }
        if let (Pane::Top, Some(cy)) = (self.pane, l.carrier_y) {
            let cw = self.text_w(f.row, scene.clock);
            outlined(dc, f.row, l.width - JUMP_PAD - cw, cy + 1 + BD, scene.clock, CLOCK_TEXT, CLOCK_EDGE);
            text(dc, f.row, JUMP_PAD, cy + 1 + BD, &scene.here_bodies, Role::Dim.rgb());
        }
    }

    fn draw_route(&self, dc: HDC, b: &RouteBox, p: &Panel) {
        let f = &self.fonts;
        let cw = f.row.char_w;
        let (left, right) = (b.x + JUMP_PAD, b.x + b.w - JUMP_PAD);
        let mut y = 1 + BD;
        for (line, rgb) in Self::route_lines(p) {
            text(dc, f.row, left, y, &self.clipped(f.row, &line, right - left), rgb);
            y += f.row.line_h;
        }
        let ahead = jump::ahead(p);
        let Some(first) = ahead.first() else { return };
        let rest = &ahead[1..];
        let lx = left + JUMP_TICK;
        let name_x = b.x + Self::stop_name_x();
        let here_mid = b.list_y + b.row_h / 2;
        let bottom = b.height - b.row_h / 2;
        let total: f64 = rest.iter().map(|l| l.ly).sum();
        let top = match &p.here {
            None => here_mid,
            Some(_) => {
                let scaled = here_mid + ((bottom - here_mid) as f64 * first.ly / (first.ly + total)).round() as i32;
                let below = i32::from(!rest.is_empty()) + i32::from(p.discovery.is_some());
                scaled.clamp(here_mid + b.row_h, (bottom - below * b.row_h).max(here_mid + b.row_h))
            }
        };
        let stops: Vec<i32> = rest
            .iter()
            .scan(0.0, |run, leg| {
                *run += leg.ly;
                Some(top + if total > 0.0 { ((bottom - top) as f64 * *run / total).round() as i32 } else { 0 })
            })
            .collect();
        let bar = |from: i32, to: i32, rgb: Rgb| {
            fill(dc, RECT { left: lx - JUMP_BAR / 2, top: from, right: lx - JUMP_BAR / 2 + JUMP_BAR, bottom: to.max(from + 1) }, rgb);
        };
        let tick = |y: i32, scoopable: bool, rgb: Rgb| {
            let t = if scoopable { ROUTE_TICK } else { ROUTE_TICK_SHORT };
            let top = y - ROUTE_TICK_H / 2;
            fill(dc, RECT { left: lx - t, top, right: lx + t + 1, bottom: top + ROUTE_TICK_H }, rgb);
        };
        let ly_at = |row_y: i32, ly: f64| {
            let ly = light_years(ly);
            let x = right - self.text_w(f.row, &ly);
            text(dc, f.row, x, row_y, &ly, Role::Dim.rgb());
            x - ROUTE_GAP_CHARS * cw
        };
        if p.here.is_some() {
            bar(here_mid, top, hop_colour(first));
        }
        for (leg, (from, to)) in rest.iter().zip(std::iter::once(top).chain(stops.iter().copied()).zip(stops.iter().copied())) {
            bar(from, to, hop_colour(leg));
        }
        if let Some(name) = &p.here {
            tick(here_mid, true, JUMP_CYAN);
            text(dc, f.row, name_x, b.list_y + 1 + BD, &self.clipped(f.row, name, right - name_x), JUMP_CYAN);
        }
        tick(top, first.scoopable, ROUTE_NEXT);
        for (leg, y) in rest.iter().zip(&stops) {
            tick(*y, leg.scoopable, JUMP_ORANGE);
        }
        let row_y = top - b.row_h / 2 + 1 + BD;
        let end = if first.ly > 0.0 { ly_at(row_y, first.ly) } else { right };
        let icon_w = if p.carrier.is_some() { JUMP_PAD + f.row.line_h } else { 0 };
        let next_name = self.clipped(f.row, &first.system, end - name_x - icon_w);
        let name_end = name_x + self.text_w(f.row, &next_name);
        text(dc, f.row, name_x, row_y, &next_name, ROUTE_NEXT);
        if let Some(open) = p.carrier {
            carrier_icon(dc, name_end + JUMP_PAD + f.row.line_h / 2, top, f.row.line_h, if open { JUMP_CARRIER } else { JUMP_CARRIER_SHUT });
        }
        let star_x = name_end + icon_w + ROUTE_GAP_CHARS * cw;
        text(dc, f.row, star_x, row_y, &self.clipped(f.row, &p.star, end - star_x), p.class_rgb);
        if let Some((found, role)) = &p.discovery {
            text(dc, f.row, star_x, row_y + b.row_h, &self.clipped(f.row, found, right - star_x), role.rgb());
        }
        if let Some(last) = rest.last() {
            let row_y = b.height - b.row_h + 1 + BD;
            let end = ly_at(row_y, jump::ahead_ly(p));
            text(dc, f.row, name_x, row_y, &self.clipped(f.row, &last.system, end - name_x), JUMP_ORANGE);
        }
    }

    fn draw_popup(&self, dc: HDC, w: i32, h: i32, b: &PopupBox, p: &RoutePopup) {
        let f = &self.fonts;
        fill(dc, RECT { left: 0, top: 0, right: w, bottom: h }, HEADER_BG);
        fill(dc, RECT { left: 0, top: b.title_h - 1, right: w, bottom: b.title_h }, HEADER_LINE);
        text(dc, f.title, (w - self.text_w(f.title, &p.title)) / 2, 1 + BD, &p.title, HEADER_TEXT);
        let star_x = POPUP_PAD + b.name_w + POPUP_GAP * f.row.char_w;
        for (r, (name, star, rgb)) in p.rows.iter().enumerate() {
            let y = b.title_h + r as i32 * b.row_h + 1 + BD;
            text(dc, f.row, POPUP_PAD, y, name, Role::Fg.rgb());
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
            Self::draw_minimap_confirmed(dc, b, d.origin, scene.dots);
            unsafe {
                let _ = IntersectClipRect(dc, 0, 0, b.w, b.h);
            }
            Self::draw_minimap_carrier(dc, b, d.origin, scene.carrier_path);
            Self::draw_minimap_route(dc, b, d.origin, &scene.route);
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
    }

    fn minimap_point(b: MiniBox, origin: [f64; 2], p: [f64; 2]) -> POINT {
        let grid = 3 * b.side;
        POINT {
            x: b.gx + ((p[0] - origin[0]) / MINIMAP_BLOCK_LY * grid as f64).round() as i32,
            y: b.gy + grid - ((p[1] - origin[1]) / MINIMAP_BLOCK_LY * grid as f64).round() as i32,
        }
    }

    fn draw_minimap_confirmed(dc: HDC, b: MiniBox, origin: [f64; 2], dots: &[(String, [f64; 3])]) {
        for (kind, p) in dots {
            let POINT { x, y } = Self::minimap_point(b, origin, [p[0], p[2]]);
            if x < 0 || y < 0 || x + MINIMAP_DOT > b.w || y + MINIMAP_DOT > b.h {
                continue;
            }
            let c = kind_colour(kind).unwrap_or(Role::Head.rgb());
            fill(dc, RECT { left: x, top: y, right: x + MINIMAP_DOT, bottom: y + MINIMAP_DOT }, c);
        }
    }

    fn draw_minimap_carrier(dc: HDC, b: MiniBox, origin: [f64; 2], path: &[[f64; 3]]) {
        let at = |p: &[f64; 3]| Self::minimap_point(b, origin, [p[0], p[2]]);
        for ends in path.windows(2) {
            line(dc, at(&ends[0]), at(&ends[1]), MINIMAP_CARRIER_W, MINIMAP_CARRIER_ROUTE);
        }
        for stop in path {
            dot(dc, at(stop), MINIMAP_CARRIER_STOP_R, MINIMAP_CARRIER_ROUTE);
        }
    }

    fn draw_minimap_route(dc: HDC, b: MiniBox, origin: [f64; 2], route: &MapRoute) {
        let at = |p: &[f64; 2]| Self::minimap_point(b, origin, *p);
        for (leg, ends) in route.legs.iter().zip(route.stops.windows(2)) {
            line(dc, at(&ends[0]), at(&ends[1]), MINIMAP_ROUTE_W, leg_colour(leg));
        }
        for (i, stop) in route.stops.iter().enumerate() {
            let behind = route.legs.get(i).is_some_and(|l| l.flown);
            dot(dc, at(stop), MINIMAP_STOP_R, if behind { JUMP_DIM } else { JUMP_ORANGE });
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
        let pad = PAD_X / 2;
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
        for (r, (cells, role)) in sheet.rows.iter().enumerate() {
            let y = head_y + b.head_h + r as i32 * b.row_h;
            for (c, cell) in cells.iter().enumerate() {
                place(dc, f.row, xs[c], xs[c + 1], y, cell, anchor(c), pad, role.rgb());
            }
        }
    }

    fn draw_table(&self, dc: HDC, b: &TableBox, t: &TargetTable, rules: bool) {
        let f = &self.fonts;
        let pad = PAD_X / 2;
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
            if row.selected {
                fill(dc, RECT { left: b.x, top: y, right: xs[t.columns.len()], bottom: y + b.row_h }, SEL_BG);
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

    pub fn mouse_up(&mut self) {
        if self.drag.take().is_some() {
            unsafe {
                let _ = ReleaseCapture();
            }
        }
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

fn make_fonts(hwnd: HWND, base: i32) -> Fonts {
    let dpi = unsafe { GetDpiForWindow(hwnd) }.max(96) as i32;
    let face = |pt: i32, bold: bool| unsafe {
        let family: Vec<u16> = FONT_FAMILY.encode_utf16().chain(std::iter::once(0)).collect();
        let font = CreateFontW(
            -(pt * dpi + 36) / 72,
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
