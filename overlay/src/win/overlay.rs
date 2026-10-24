use windows::Win32::Foundation::{COLORREF, HWND, LPARAM, LRESULT, POINT, RECT, SIZE, WPARAM};
use windows::Win32::Graphics::Gdi::{
    AC_SRC_ALPHA, AC_SRC_OVER, BI_RGB, CreatePen, LineTo, MoveToEx, PS_SOLID, Polygon, BITMAPINFO, BITMAPINFOHEADER, BLENDFUNCTION, BeginPaint, CLIP_DEFAULT_PRECIS,
    CreateCompatibleDC, CreateDIBSection, CreateFontW, CreateSolidBrush, DEFAULT_CHARSET, DEFAULT_QUALITY,
    DIB_RGB_COLORS, DeleteDC, DeleteObject, EndPaint, FF_MODERN, FIXED_PITCH, FW_BOLD, FW_NORMAL, FillRect, GdiFlush,
    GetDC, GetTextExtentPoint32W, GetTextMetricsW, HDC, HFONT, HGDIOBJ, OUT_DEFAULT_PRECIS, PAINTSTRUCT, ReleaseDC,
    SelectObject, SetBkMode, SetTextColor, TEXTMETRICW, TRANSPARENT, TextOutW,
};
use windows::Win32::System::LibraryLoader::GetModuleHandleW;
use windows::Win32::UI::HiDpi::GetDpiForWindow;
use windows::Win32::UI::WindowsAndMessaging::{GetSystemMetrics, SM_CXSCREEN};
use windows::Win32::UI::Input::KeyboardAndMouse::{GetCapture, ReleaseCapture, SetCapture};
use windows::Win32::UI::WindowsAndMessaging::{
    CS_HREDRAW, CS_VREDRAW, CreateWindowExW, DefWindowProcW, GetCursorPos, GetWindowRect, HWND_TOPMOST,
    IDC_ARROW, LoadCursorW, RegisterClassExW, SW_HIDE, SW_SHOWNOACTIVATE, SWP_NOACTIVATE, SWP_NOMOVE, SWP_NOSIZE,
    SWP_NOZORDER, SetTimer, SetWindowPos, ShowWindow, ULW_ALPHA, UpdateLayeredWindow, WNDCLASSEXW, WS_EX_LAYERED,
    WS_EX_NOACTIVATE, WS_EX_TOOLWINDOW, WS_EX_TOPMOST, WS_POPUP,
};
use windows::core::{PCWSTR, w};

use crate::jump::{self, Panel};
use crate::table::TargetTable;
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

fn apply_alpha(pixels: &mut [u32], opacity: u8) {
    let key = dib_rgb(KEY);
    let band = dib_rgb(HEADER_BG);
    let band_alpha = (opacity as f64 * HEADER_ALPHA).round() as u32;
    for p in pixels {
        let rgb = *p & 0x00ff_ffff;
        let a = if rgb == key {
            0
        } else if rgb == band {
            band_alpha
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
    big: Face,
    big_plain: Face,
}

#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub enum Pane {
    Left,
    Top,
}

pub struct Scene<'a> {
    pub confirmed: &'a TargetTable,
    pub nearest: &'a TargetTable,
    pub sector: &'a TargetTable,
    pub clock: &'a str,
    pub carrier: &'a [String; 3],
    pub carrier_role: Role,
    pub jump: Option<&'a Panel>,
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
    chrome_h: i32,
    confirmed: Option<TableBox>,
    nearest: Option<TableBox>,
    sector: Option<TableBox>,
    jump: Option<(i32, i32)>,
    footer_y: i32,
    carrier_y: Option<i32>,
}

pub struct Overlay {
    pub hwnd: HWND,
    pane: Pane,
    centre_x: Option<i32>,
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
        title: &str,
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
            let title_w: Vec<u16> = title.encode_utf16().chain(std::iter::once(0)).collect();
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
            let x = centre_x.unwrap_or_else(|| pos.0.unwrap_or_else(|| scale(EDGE_MARGIN)));
            let y = pos.1.unwrap_or_else(|| scale(EDGE_MARGIN));
            let _ = SetWindowPos(hwnd, Some(HWND_TOPMOST), x, y, 0, 0, SWP_NOSIZE | SWP_NOACTIVATE);
            Ok(Overlay {
                hwnd,
                pane,
                centre_x,
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

    pub fn refresh(&mut self, scene: &Scene) {
        let layout = self.layout(scene);
        if (layout.width, layout.height) != self.size {
            self.size = (layout.width, layout.height);
            unsafe {
                match self.centre_x {
                    Some(cx) => {
                        let mut r = RECT::default();
                        let _ = GetWindowRect(self.hwnd, &mut r);
                        let _ = SetWindowPos(
                            self.hwnd,
                            None,
                            cx - layout.width / 2,
                            r.top,
                            layout.width,
                            layout.height,
                            SWP_NOZORDER | SWP_NOACTIVATE,
                        );
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
        let row_h = Self::label_h(f.row);
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
            width,
            height: footer_y + footer_h,
            chrome_h,
            confirmed: None,
            nearest: None,
            sector: Some(sector),
            jump: None,
            footer_y,
            carrier_y: None,
        }
    }

    fn jump_h(&self) -> i32 {
        let f = &self.fonts;
        JUMP_RULE * 2 + f.big.line_h + JUMP_GAP + JUMP_TICK * 2 + JUMP_GAP / 2 + f.row.line_h
    }

    fn layout_top(&self, scene: &Scene) -> Layout {
        let f = &self.fonts;
        let confirmed = scene.confirmed.visible.then(|| self.table_box(scene.confirmed));
        let nearest = scene.nearest.visible.then(|| self.table_box(scene.nearest));
        let gap = if confirmed.is_some() && nearest.is_some() { TOP_TABLE_GAP * f.row.char_w } else { 0 };
        let top_w = confirmed.as_ref().map_or(0, |b| b.width) + gap + nearest.as_ref().map_or(0, |b| b.width);
        let top_h = confirmed.as_ref().map_or(0, |b| b.height).max(nearest.as_ref().map_or(0, |b| b.height));
        let header_w = scene.jump.map_or(0, |p| {
            let counts = self.text_w(f.big_plain, &p.counts);
            let side = self.text_w(f.big, &p.target).max(self.text_w(f.big, &p.star));
            2 * side + counts + 2 * JUMP_PAD + 2 * JUMP_MIN_GAP * f.big.char_w
        });
        let width = top_w.max(JUMP_MIN_W * f.small.char_w).max(header_w);
        let mut confirmed = confirmed;
        let mut nearest = nearest;
        if let Some(b) = confirmed.as_mut() {
            b.x = 0;
        }
        if let Some(b) = nearest.as_mut() {
            b.x = width - b.width;
        }
        let mut y = top_h;
        let jump = scene.jump.map(|_| {
            let h = self.jump_h();
            let at = (y, h);
            y += h;
            at
        });
        let has_carrier = !scene.carrier.iter().all(String::is_empty);
        let carrier_y = has_carrier.then_some(y + FOOTER_GAP);
        let height = carrier_y.map_or(y, |c| c + Self::label_h(f.row));
        Layout {
            width,
            height: height.max(1),
            chrome_h: 0,
            confirmed,
            nearest,
            sector: None,
            jump,
            footer_y: height,
            carrier_y,
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
                SetBkMode(mem, TRANSPARENT);
                self.draw(mem, &layout, scene);
                let _ = GdiFlush();
                apply_alpha(std::slice::from_raw_parts_mut(bits as *mut u32, (w * h) as usize), self.opacity);
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
        if self.chrome && self.pane == Pane::Left {
            text(dc, f.title, 1 + BD, 1 + BD, "::: Explorers Companion :::", Role::Head.rgb());
            let sw = self.text_w(f.small, &self.status);
            text(dc, f.small, l.width - 2 - BD - 1 - sw, 1 + BD, &self.status, Role::Dim.rgb());
        }
        if let Some(b) = &l.confirmed {
            self.draw_table(dc, b, scene.confirmed);
        }
        if let Some(b) = &l.nearest {
            self.draw_table(dc, b, scene.nearest);
        }
        if let Some(b) = &l.sector {
            self.draw_table(dc, b, scene.sector);
        }
        if let (Some((y, h)), Some(panel)) = (l.jump, scene.jump) {
            self.draw_jump(dc, y, h, l.width, panel);
        }
        if let Some(cy) = l.carrier_y {
            let [here, state, to] = scene.carrier;
            let y = cy + 1 + BD;
            text(dc, f.row, JUMP_PAD, y, here, Role::Carrier.rgb());
            text(dc, f.row, (l.width - self.text_w(f.row, state)) / 2, y, state, scene.carrier_role.rgb());
            text(dc, f.row, l.width - JUMP_PAD - self.text_w(f.row, to), y, to, Role::Carrier.rgb());
        }
        if self.chrome && self.pane == Pane::Left && !self.footer.0.is_empty() {
            text(dc, f.small, 1 + BD, l.footer_y + 1 + BD, &self.footer.0, self.footer.1.rgb());
        }
        if self.pane == Pane::Top && !scene.clock.is_empty() {
            let cw = self.text_w(f.head, scene.clock);
            let right = l.width - PAD_X / 2 - BD - 1;
            text(dc, f.head, right - cw, 1 + BD, scene.clock, Role::Clock.rgb());
        }
        let _ = l.chrome_h;
    }

    fn draw_jump(&self, dc: HDC, top: i32, h: i32, w: i32, p: &Panel) {
        let f = &self.fonts;
        let (left, right) = (JUMP_PAD, w - JUMP_PAD);
        for (dy, c) in [(1, JUMP_DIM), (2, JUMP_ORANGE), (3, JUMP_DIM)] {
            fill(dc, RECT { left: 2, top: top + dy, right: w - 2, bottom: top + dy + 1 }, c);
            fill(dc, RECT { left: 2, top: top + h - 1 - dy, right: w - 2, bottom: top + h - dy }, c);
        }
        let head_y = top + JUMP_RULE;
        text(dc, f.big, left, head_y, &p.target, JUMP_ORANGE);
        if !p.star.is_empty() {
            text(dc, f.big, right - self.text_w(f.big, &p.star), head_y, &p.star, p.class_rgb);
        }
        if !p.counts.is_empty() {
            text(dc, f.big_plain, (w - self.text_w(f.big_plain, &p.counts)) / 2, head_y, &p.counts, Role::Dim.rgb());
        }
        let bar_y = head_y + f.big.line_h + JUMP_GAP;
        let bar_h = JUMP_TICK * 2;
        let hop = format!("#{} of {}", p.hop, p.hops);
        let total = jump::total_text(p.total_ly);
        let text_y = bar_y + bar_h + JUMP_GAP / 2;
        text(dc, f.row, left, text_y, &hop, JUMP_ORANGE);
        text(dc, f.row, right - self.text_w(f.row, &total), text_y, &total, JUMP_ORANGE);
        if let Some((line, role)) = &p.discovery {
            text(dc, f.row, (w - self.text_w(f.row, line)) / 2, text_y, line, role.rgb());
        }
        let (x0, x1) = (left, right);
        let mid = bar_y + bar_h / 2;
        let sum: f64 = p.legs.iter().map(|l| l.ly).sum();
        let scale = |d: f64| x0 + if sum > 0.0 { ((x1 - x0) as f64 * d / sum).round() as i32 } else { 0 };
        thick(dc, POINT { x: x0, y: mid }, POINT { x: x1, y: mid }, JUMP_BAR, JUMP_DIM);
        let mut run = 0.0;
        let mut ends = Vec::with_capacity(p.legs.len());
        for leg in &p.legs {
            let (a, b) = (scale(run), scale(run + leg.ly));
            run += leg.ly;
            let colour = match (leg.next, leg.flown, leg.boosted) {
                (true, ..) => Some(JUMP_CYAN),
                (_, true, true) => Some(JUMP_TEAL_DIM),
                (_, false, true) => Some(JUMP_TEAL),
                _ => None,
            };
            if let Some(c) = colour {
                thick(dc, POINT { x: a, y: mid }, POINT { x: b, y: mid }, JUMP_BAR, c);
            }
            ends.push((a, b, leg));
        }
        fill(dc, RECT { left: x0, top: mid - JUMP_TICK / 2, right: x0 + 1, bottom: mid + JUMP_TICK / 2 + 1 }, JUMP_ORANGE);
        for (_, b, leg) in &ends {
            let t = if leg.scoopable { JUMP_TICK } else { JUMP_TICK / 2 };
            let c = if leg.flown { JUMP_DIM } else { JUMP_ORANGE };
            fill(dc, RECT { left: *b, top: mid - t, right: b + 1, bottom: mid + t + 1 }, c);
        }
        if let Some((a, b, _)) = ends.iter().find(|(_, _, l)| l.next) {
            fill(dc, RECT { left: a - 1, top: mid - JUMP_TICK, right: a + 1, bottom: mid + JUMP_TICK + 1 }, JUMP_CYAN);
            let arm = JUMP_TICK - 2;
            segment(dc, POINT { x: b - arm, y: mid - arm }, POINT { x: *b, y: mid }, JUMP_CYAN);
            segment(dc, POINT { x: b - arm, y: mid + arm }, POINT { x: *b, y: mid }, JUMP_CYAN);
            segment(dc, POINT { x: b - arm - 1, y: mid - arm }, POINT { x: b - 1, y: mid }, JUMP_CYAN);
            segment(dc, POINT { x: b - arm - 1, y: mid + arm }, POINT { x: b - 1, y: mid }, JUMP_CYAN);
        }
    }

    fn draw_table(&self, dc: HDC, b: &TableBox, t: &TargetTable) {
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
            for (c, cell) in row.cells.iter().enumerate() {
                if let Some(off) = cell.cube {
                    cube_icon(dc, xs[c], xs[c + 1], y, b.row_h, off);
                }
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

fn quad(dc: HDC, pts: [POINT; 4], fill: Rgb, line: Rgb) {
    unsafe {
        let brush = CreateSolidBrush(colorref(fill));
        let pen = CreatePen(PS_SOLID, 1, colorref(line));
        let old_brush = SelectObject(dc, HGDIOBJ(brush.0));
        let old_pen = SelectObject(dc, HGDIOBJ(pen.0));
        let _ = Polygon(dc, &pts);
        SelectObject(dc, old_pen);
        SelectObject(dc, old_brush);
        let _ = DeleteObject(HGDIOBJ(pen.0));
        let _ = DeleteObject(HGDIOBJ(brush.0));
    }
}

fn thick(dc: HDC, a: POINT, b: POINT, width: i32, c: Rgb) {
    fill(dc, RECT { left: a.x.min(b.x), top: a.y - width / 2, right: a.x.max(b.x) + 1, bottom: a.y - width / 2 + width }, c);
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

fn cube_icon(dc: HDC, left: i32, right: i32, top: i32, row_h: i32, off: [i64; 3]) {
    let h = row_h - 2;
    let ch = (h / 6).max(2);
    let (cw, sk) = (2 * ch, ch);
    let x0 = left + (right - left - 3 * (cw + sk)) / 2;
    let dy = off[1] as i32;
    let pad = (h - 6 * ch) / 2;
    let base = top + 1 + match dy {
        1 => h - pad,
        -1 => pad + 3 * ch,
        _ => h / 2 + 3 * ch / 2,
    };
    let at = |u: i32, v: i32, lift: i32| POINT { x: x0 + u * cw + v * sk, y: base - v * ch - lift };
    let cell = |i: i32, j: i32, lift: i32| [at(i, j, lift), at(i + 1, j, lift), at(i + 1, j + 1, lift), at(i, j + 1, lift)];
    let centre = |i: i32, j: i32, lift: i32| {
        let p = cell(i, j, lift);
        POINT { x: (p[0].x + p[2].x) / 2, y: (p[0].y + p[2].y) / 2 }
    };
    let (ti, tj) = (off[0] as i32 + 1, off[2] as i32 + 1);
    for j in (0..3).rev() {
        for i in 0..3 {
            let fill = match (i, j) {
                _ if (i, j) == (ti, tj) && dy == 0 => CUBE_TARGET,
                _ if (i, j) == (ti, tj) => CUBE_FOOTPRINT,
                (1, 1) => continue,
                _ => CUBE_CELL,
            };
            quad(dc, cell(i, j, 0), fill, CUBE_LINE);
        }
    }
    if dy != 0 {
        let lift = dy * 3 * ch;
        segment(dc, centre(ti, tj, 0), centre(ti, tj, lift), CUBE_TARGET);
        quad(dc, cell(ti, tj, lift), CUBE_TARGET, CUBE_TARGET);
    }
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
        big: face(base + 3, true),
        big_plain: face(base + 3, false),
    }
}
