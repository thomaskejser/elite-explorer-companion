use windows::Win32::Foundation::{COLORREF, HWND, LPARAM, LRESULT, POINT, RECT, SIZE, WPARAM};
use windows::Win32::Graphics::Gdi::{
    BeginPaint, BitBlt, CLIP_DEFAULT_PRECIS, CreateCompatibleBitmap, CreateCompatibleDC, CreateFontW,
    CreateSolidBrush, DEFAULT_CHARSET, DEFAULT_QUALITY, DeleteDC, DeleteObject, EndPaint, FF_MODERN,
    FIXED_PITCH, FW_BOLD, FW_NORMAL, FillRect, GetDC, GetTextExtentPoint32W, GetTextMetricsW, HDC, HFONT,
    HGDIOBJ, InvalidateRect, OUT_DEFAULT_PRECIS, PAINTSTRUCT, ReleaseDC, SRCCOPY, SelectObject, SetBkMode,
    SetTextColor, TEXTMETRICW, TRANSPARENT, TextOutW,
};
use windows::Win32::System::LibraryLoader::GetModuleHandleW;
use windows::Win32::UI::HiDpi::GetDpiForWindow;
use windows::Win32::UI::Input::KeyboardAndMouse::{GetCapture, ReleaseCapture, SetCapture};
use windows::Win32::UI::WindowsAndMessaging::{
    CS_HREDRAW, CS_VREDRAW, CreateWindowExW, DefWindowProcW, GetCursorPos, GetWindowRect, HWND_TOPMOST,
    IDC_ARROW, LWA_ALPHA, LWA_COLORKEY, LoadCursorW, RegisterClassExW, SW_HIDE, SW_SHOWNOACTIVATE,
    SWP_NOACTIVATE, SWP_NOMOVE, SWP_NOSIZE, SWP_NOZORDER, SetLayeredWindowAttributes, SetTimer, SetWindowPos,
    ShowWindow, WNDCLASSEXW, WS_EX_LAYERED, WS_EX_NOACTIVATE, WS_EX_TOOLWINDOW, WS_EX_TOPMOST, WS_POPUP,
};
use windows::core::{PCWSTR, w};

use crate::table::TargetTable;
use crate::theme::*;
use crate::win::hotkeys::Segment;

pub const TICK_TIMER: usize = 1;
pub const FLASH_TIMER: usize = 2;

const BD: i32 = 2;

fn colorref(c: Rgb) -> COLORREF {
    COLORREF(c.0 as u32 | (c.1 as u32) << 8 | (c.2 as u32) << 16)
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

pub struct Scene<'a> {
    pub confirmed: &'a TargetTable,
    pub nearest: &'a TargetTable,
    pub sector: &'a TargetTable,
    pub adjacent: &'a TargetTable,
    pub clock: &'a str,
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
    top_y: i32,
    top_h: i32,
    confirmed: Option<TableBox>,
    nearest: Option<TableBox>,
    sector: TableBox,
    adjacent: Option<TableBox>,
    help_y: i32,
    help_cols: Vec<i32>,
    help_row_h: i32,
    footer_y: i32,
}

pub struct Overlay {
    pub hwnd: HWND,
    fonts: Fonts,
    base_pt: i32,
    pub chrome: bool,
    draggable: bool,
    shown: bool,
    status: String,
    footer: (String, Role),
    help: Vec<Vec<Vec<Segment>>>,
    size: (i32, i32),
    drag: Option<(POINT, RECT)>,
}

impl Overlay {
    pub fn create(
        title: &str,
        font_pt: i32,
        opacity: f64,
        pos: (Option<i32>, Option<i32>),
        draggable: bool,
        chrome: bool,
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
            SetLayeredWindowAttributes(
                hwnd,
                colorref(KEY),
                (opacity.clamp(0.0, 1.0) * 255.0).round() as u8,
                LWA_COLORKEY | LWA_ALPHA,
            )
            .map_err(|e| e.to_string())?;
            let fonts = make_fonts(hwnd, font_pt);
            let scale = |v: i32| v * GetDpiForWindow(hwnd) as i32 / 96;
            let x = pos.0.unwrap_or_else(|| scale(EDGE_MARGIN));
            let y = pos.1.unwrap_or_else(|| scale(EDGE_MARGIN));
            let _ = SetWindowPos(hwnd, Some(HWND_TOPMOST), x, y, 0, 0, SWP_NOSIZE | SWP_NOACTIVATE);
            Ok(Overlay {
                hwnd,
                fonts,
                base_pt: font_pt,
                chrome,
                draggable,
                shown: false,
                status: String::new(),
                footer: (String::new(), Role::Dim),
                help: Vec::new(),
                size: (0, 0),
                drag: None,
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
        if self.chrome {
            self.status = text;
        }
    }

    pub fn set_footer(&mut self, text: &str, role: Role) {
        if self.chrome {
            self.footer = (text.to_string(), role);
        }
    }

    pub fn set_help(&mut self, rows: Vec<Vec<Vec<Segment>>>) {
        self.help = rows;
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
        unsafe {
            let _ = InvalidateRect(Some(self.hwnd), None, false);
        }
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
            height: title_h + head_h + row_h * t.n_rows as i32,
        }
    }

    fn layout(&self, scene: &Scene) -> Layout {
        let f = &self.fonts;
        let chrome_h = if self.chrome { Self::label_h(f.title).max(Self::label_h(f.small)) } else { 0 };
        let confirmed = scene.confirmed.visible.then(|| self.table_box(scene.confirmed));
        let nearest = scene.nearest.visible.then(|| self.table_box(scene.nearest));
        let mut sector = self.table_box(scene.sector);
        let adjacent = scene.adjacent.visible.then(|| self.table_box(scene.adjacent));
        let top_w = confirmed.as_ref().map_or(0, |b| b.width) + nearest.as_ref().map_or(0, |b| b.width);
        let top_h = confirmed.as_ref().map_or(0, |b| b.height).max(nearest.as_ref().map_or(0, |b| b.height));
        let mut width = top_w.max(sector.width).max(adjacent.as_ref().map_or(0, |b| b.width));
        if self.chrome {
            let bar = self.label_w(f.title, "::: sector rares :::", 1) + self.label_w(f.small, &self.status, 1) + 10;
            width = width.max(bar);
        }
        let top_y = chrome_h;
        let mut confirmed = confirmed;
        let mut nearest = nearest;
        if let Some(b) = confirmed.as_mut() {
            b.x = 0;
            b.y = top_y;
        }
        if let Some(b) = nearest.as_mut() {
            b.x = width - b.width;
            b.y = top_y;
        }
        sector.y = top_y + top_h;
        let mut y = sector.y + sector.height;
        let mut adjacent = adjacent;
        if let Some(b) = adjacent.as_mut() {
            b.y = y;
            y += b.height;
        }
        let help_row_h = Self::label_h(f.small);
        let help_cols = self.help_columns();
        let help_y = y + HELP_GAP;
        let footer_y = help_y + help_row_h * self.help.len() as i32;
        let footer_h = if self.chrome { Self::label_h(f.small) } else { 0 };
        Layout {
            width,
            height: footer_y + footer_h,
            chrome_h,
            top_y,
            top_h,
            confirmed,
            nearest,
            sector,
            adjacent,
            help_y,
            help_cols,
            help_row_h,
            footer_y,
        }
    }

    fn cell_w(&self, segments: &[Segment]) -> i32 {
        segments.iter().map(|(text, _)| self.label_w(self.fonts.small, text, 1)).sum()
    }

    fn help_columns(&self) -> Vec<i32> {
        let width = self.help.iter().map(Vec::len).max().unwrap_or(0);
        let mut cols = vec![0; width];
        for cells in &self.help {
            let filled: Vec<usize> = (0..cells.len()).filter(|&c| !cells[c].is_empty()).collect();
            for (i, &c) in filled.iter().enumerate() {
                let next = filled.get(i + 1).copied().unwrap_or(width);
                if next - c == 1 {
                    let w = self.cell_w(&cells[c]) + HELP_PAD[c % HELP_PAD.len()];
                    cols[c] = cols[c].max(w);
                }
            }
        }
        cols
    }

    pub fn paint(&self, scene: &Scene) {
        unsafe {
            let mut ps = PAINTSTRUCT::default();
            let hdc = BeginPaint(self.hwnd, &mut ps);
            let layout = self.layout(scene);
            let (w, h) = (layout.width.max(1), layout.height.max(1));
            let mem = CreateCompatibleDC(Some(hdc));
            let bmp = CreateCompatibleBitmap(hdc, w, h);
            let old_bmp = SelectObject(mem, HGDIOBJ(bmp.0));
            fill(mem, RECT { left: 0, top: 0, right: w, bottom: h }, KEY);
            SetBkMode(mem, TRANSPARENT);
            self.draw(mem, &layout, scene);
            let _ = BitBlt(hdc, 0, 0, w, h, Some(mem), 0, 0, SRCCOPY);
            SelectObject(mem, old_bmp);
            let _ = DeleteObject(HGDIOBJ(bmp.0));
            let _ = DeleteDC(mem);
            let _ = EndPaint(self.hwnd, &ps);
        }
    }

    fn draw(&self, dc: HDC, l: &Layout, scene: &Scene) {
        let f = &self.fonts;
        if self.chrome {
            text(dc, f.title, 1 + BD, 1 + BD, "::: sector rares :::", Role::Head.rgb());
            let sw = self.text_w(f.small, &self.status);
            text(dc, f.small, l.width - 2 - BD - 1 - sw, 1 + BD, &self.status, Role::Dim.rgb());
        }
        if let Some(b) = &l.confirmed {
            self.draw_table(dc, b, scene.confirmed);
        }
        if let Some(b) = &l.nearest {
            self.draw_table(dc, b, scene.nearest);
        }
        self.draw_table(dc, &l.sector, scene.sector);
        if let Some(b) = &l.adjacent {
            self.draw_table(dc, b, scene.adjacent);
        }
        let mut y = l.help_y;
        for cells in &self.help {
            let mut x = 0;
            for (c, segments) in cells.iter().enumerate() {
                let mut sx = x;
                for (t, role) in segments {
                    text(dc, f.small, sx + 1 + BD, y + 1 + BD, t, role.rgb());
                    sx += self.label_w(f.small, t, 1);
                }
                x += l.help_cols.get(c).copied().unwrap_or(0);
            }
            y += l.help_row_h;
        }
        if self.chrome && !self.footer.0.is_empty() {
            text(dc, f.small, 1 + BD, l.footer_y + 1 + BD, &self.footer.0, self.footer.1.rgb());
        }
        if l.top_h > 0 && !scene.clock.is_empty() {
            let cw = self.text_w(f.title, scene.clock);
            let right = l.width - PAD_X / 2 - BD - 1;
            text(dc, f.title, right - cw, l.top_y + 1 + BD, scene.clock, Role::Clock.rgb());
        }
        let _ = l.chrome_h;
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
        for (c, col) in t.columns.iter().enumerate() {
            place(dc, f.head, xs[c], xs[c + 1], head_y, col.heading, col.anchor, pad, Role::Head.rgb());
        }
        let span = t.span();
        for (r, row) in t.draw_rows().into_iter().enumerate() {
            let y = head_y + b.head_h + r as i32 * b.row_h;
            if row.selected {
                fill(dc, RECT { left: b.x, top: y, right: xs[t.columns.len()], bottom: y + b.row_h }, SEL_BG);
            }
            for (c, cell) in row.cells.iter().enumerate() {
                if cell.shown && !cell.text.is_empty() {
                    place(dc, f.row, xs[c], xs[c + 1], y, &cell.text, t.columns[c].anchor, pad, cell.fg);
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
        let Some((p0, r0)) = self.drag else { return };
        unsafe {
            if GetCapture() != self.hwnd {
                self.drag = None;
                return;
            }
            let mut p = POINT::default();
            if GetCursorPos(&mut p).is_ok() {
                let _ = SetWindowPos(
                    self.hwnd,
                    None,
                    r0.left + p.x - p0.x,
                    r0.top + p.y - p0.y,
                    0,
                    0,
                    SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE,
                );
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
