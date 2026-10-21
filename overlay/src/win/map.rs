use windows::Win32::Foundation::{HINSTANCE, HWND, LPARAM, LRESULT, RECT, SIZE, WPARAM};
use windows::Win32::Graphics::Gdi::{
    BI_RGB, BITMAPINFO, BITMAPINFOHEADER, BeginPaint, BitBlt, CreateCompatibleDC, CreateDIBSection, DIB_RGB_COLORS,
    DT_CENTER, DT_LEFT, DT_NOPREFIX, DT_SINGLELINE, DT_VCENTER, DT_WORDBREAK, DeleteDC, DeleteObject, DrawTextW, EndPaint,
    GdiFlush, GetTextExtentPoint32W, HDC, HFONT, HGDIOBJ, InvalidateRect, PAINTSTRUCT, SRCCOPY, SelectObject, SetBkMode, SetTextColor,
    TRANSPARENT,
};
use windows::Win32::System::LibraryLoader::GetModuleHandleW;
use windows::Win32::UI::Controls::WM_MOUSELEAVE;
use windows::Win32::UI::Input::KeyboardAndMouse::{TME_LEAVE, TRACKMOUSEEVENT, TrackMouseEvent};
use windows::Win32::UI::WindowsAndMessaging::{
    CreateWindowExW, DefWindowProcW, GetClientRect, IDC_ARROW, LoadCursorW, RegisterClassExW, WINDOW_EX_STYLE,
    WM_ERASEBKGND, WM_LBUTTONDOWN, WM_MOUSEMOVE, WM_PAINT, WNDCLASSEXW, WS_CHILD, WS_CLIPSIBLINGS,
};
use windows::core::{PCWSTR, w};

use crate::database::{DENSITY_GRID, MAP_GRID, MapGrid, RegionExpected};
use crate::kinds::KINDS;
use crate::table::{thousands, thousands_i};
use crate::theme::{
    HEADER_LINE, HEADER_TEXT, MAP_BORDER, MAP_GRADIENT, MAP_LABEL, MAP_SELECTED, MAP_SPACE, MAP_STARS, Rgb,
    TABLE_ROW, TABLE_TEXT,
};

use super::expected_table::{colorref, fill};
use super::main_window;

const REGIONS: usize = 256;
const MARGIN_CELLS: usize = 24;

pub struct MapLayout {
    pub top: i32,
    pub right: i32,
    pub caption: i32,
    pub info_left: i32,
}

struct Region {
    name: String,
    systems: i64,
    p: [f64; KINDS.len()],
    centre: (f64, f64),
}

struct Cache {
    w: i32,
    h: i32,
    ids: Vec<u8>,
    density: Vec<f32>,
    border: Vec<bool>,
}

pub struct MapView {
    pub hwnd: HWND,
    grid: Option<Box<MapGrid>>,
    regions: Vec<Option<Region>>,
    bounds: (usize, usize, usize, usize),
    kind: usize,
    selected: Option<u8>,
    hover: Option<u8>,
    cache: Option<Cache>,
    font: HFONT,
    small: HFONT,
    layout: MapLayout,
    tracking: bool,
}

fn lerp(a: Rgb, b: Rgb, t: f64) -> Rgb {
    let m = |x: u8, y: u8| (x as f64 + (y as f64 - x as f64) * t).round() as u8;
    Rgb(m(a.0, b.0), m(a.1, b.1), m(a.2, b.2))
}

fn scale(c: Rgb, f: f64) -> Rgb {
    let m = |x: u8| (x as f64 * f).round().clamp(0.0, 255.0) as u8;
    Rgb(m(c.0), m(c.1), m(c.2))
}

pub fn gradient(t: f64) -> Rgb {
    let t = t.clamp(0.0, 1.0) * (MAP_GRADIENT.len() - 1) as f64;
    let i = (t.floor() as usize).min(MAP_GRADIENT.len() - 2);
    lerp(MAP_GRADIENT[i], MAP_GRADIENT[i + 1], t - i as f64)
}

fn dib(c: Rgb) -> u32 {
    (c.0 as u32) << 16 | (c.1 as u32) << 8 | c.2 as u32
}

fn text_width(dc: HDC, font: HFONT, s: &str) -> i32 {
    let t: Vec<u16> = s.encode_utf16().collect();
    let mut size = SIZE::default();
    unsafe {
        let old = SelectObject(dc, HGDIOBJ(font.0));
        let _ = GetTextExtentPoint32W(dc, &t, &mut size);
        SelectObject(dc, old);
    }
    size.cx
}

fn draw_wrapped(dc: HDC, font: HFONT, r: RECT, s: &str, c: Rgb) {
    let mut t: Vec<u16> = s.encode_utf16().collect();
    let mut r = r;
    unsafe {
        let old = SelectObject(dc, HGDIOBJ(font.0));
        SetTextColor(dc, colorref(c));
        DrawTextW(dc, &mut t, &mut r, DT_WORDBREAK | DT_NOPREFIX | DT_LEFT);
        SelectObject(dc, old);
    }
}

fn draw_text(dc: HDC, font: HFONT, r: RECT, s: &str, c: Rgb, centre: bool) {
    let mut t: Vec<u16> = s.encode_utf16().collect();
    let mut r = r;
    unsafe {
        let old = SelectObject(dc, HGDIOBJ(font.0));
        SetTextColor(dc, colorref(c));
        let align = if centre { DT_CENTER } else { DT_LEFT };
        DrawTextW(dc, &mut t, &mut r, DT_SINGLELINE | DT_VCENTER | DT_NOPREFIX | align);
        SelectObject(dc, old);
    }
}

impl MapView {
    pub fn create(parent: HWND, instance: HINSTANCE) -> Result<MapView, String> {
        unsafe {
            let class = WNDCLASSEXW {
                cbSize: std::mem::size_of::<WNDCLASSEXW>() as u32,
                lpfnWndProc: Some(wndproc),
                hInstance: GetModuleHandleW(None).map_err(|e| e.to_string())?.into(),
                hCursor: LoadCursorW(None, IDC_ARROW).unwrap_or_default(),
                lpszClassName: w!("EdOverlayMap"),
                ..Default::default()
            };
            RegisterClassExW(&class);
            let hwnd = CreateWindowExW(
                WINDOW_EX_STYLE::default(),
                w!("EdOverlayMap"),
                PCWSTR::null(),
                WS_CHILD | WS_CLIPSIBLINGS,
                0,
                0,
                0,
                0,
                Some(parent),
                None,
                Some(instance),
                None,
            )
            .map_err(|e| e.to_string())?;
            Ok(MapView {
                hwnd,
                grid: None,
                regions: (0..REGIONS).map(|_| None).collect(),
                bounds: (0, 0, MAP_GRID - 1, MAP_GRID - 1),
                kind: 0,
                selected: None,
                hover: None,
                cache: None,
                font: HFONT::default(),
                small: HFONT::default(),
                layout: MapLayout { top: 0, right: 0, caption: 0, info_left: 0 },
                tracking: false,
            })
        }
    }

    pub fn set_fonts(&mut self, font: HFONT, small: HFONT) {
        self.font = font;
        self.small = small;
        self.invalidate();
    }

    pub fn set_layout(&mut self, layout: MapLayout) {
        self.layout = layout;
        self.cache = None;
        self.invalidate();
    }

    pub fn set_kind(&mut self, kind: usize) {
        self.kind = kind;
        self.invalidate();
    }

    pub fn kind(&self) -> usize {
        self.kind
    }

    pub fn selected_region(&self) -> Option<i64> {
        self.selected.map(i64::from)
    }

    pub fn selected_total(&self, label: &str) -> Option<RegionExpected> {
        let id = self.selected?;
        let r = self.regions[id as usize].as_ref()?;
        Some(RegionExpected { region: label.to_string(), id: Some(id as i64), systems: r.systems, known: 0, p: r.p })
    }

    pub fn show_grid(&mut self, grid: MapGrid) {
        let mut sums = vec![(0f64, 0f64, 0f64); REGIONS];
        let (mut x0, mut z0, mut x1, mut z1) = (MAP_GRID, MAP_GRID, 0, 0);
        for z in 0..MAP_GRID {
            for x in 0..MAP_GRID {
                let id = grid.regions[z * MAP_GRID + x] as usize;
                if id == 0 {
                    continue;
                }
                let s = &mut sums[id];
                s.0 += x as f64;
                s.1 += z as f64;
                s.2 += 1.0;
                (x0, z0, x1, z1) = (x0.min(x), z0.min(z), x1.max(x), z1.max(z));
            }
        }
        if x1 >= x0 {
            self.bounds = (
                x0.saturating_sub(MARGIN_CELLS),
                z0.saturating_sub(MARGIN_CELLS),
                (x1 + MARGIN_CELLS).min(MAP_GRID - 1),
                (z1 + MARGIN_CELLS).min(MAP_GRID - 1),
            );
        }
        for (id, s) in sums.iter().enumerate() {
            if s.2 > 0.0 {
                let r = self.regions[id].get_or_insert_with(|| Region {
                    name: String::new(),
                    systems: 0,
                    p: [0.0; KINDS.len()],
                    centre: (0.0, 0.0),
                });
                r.centre = (s.0 / s.2, s.1 / s.2);
            }
        }
        self.grid = Some(Box::new(grid));
        self.cache = None;
        self.invalidate();
    }

    pub fn show_regions(&mut self, rows: &[RegionExpected]) {
        for row in rows {
            let Some(id) = row.id.filter(|&i| (1..REGIONS as i64).contains(&i)) else { continue };
            let r = self.regions[id as usize].get_or_insert_with(|| Region {
                name: String::new(),
                systems: 0,
                p: [0.0; KINDS.len()],
                centre: (0.0, 0.0),
            });
            r.name = row.region.clone();
            r.systems = row.systems;
            r.p = row.p;
        }
        self.invalidate();
    }

    fn invalidate(&self) {
        unsafe {
            let _ = InvalidateRect(Some(self.hwnd), None, false);
        }
    }

    fn map_rect(&self) -> RECT {
        let mut c = RECT::default();
        unsafe {
            let _ = GetClientRect(self.hwnd, &mut c);
        }
        RECT { top: self.layout.top, right: c.right - self.layout.right, ..c }
    }

    fn viewport(&self, r: RECT) -> (f64, f64, f64) {
        let (x0, z0, x1, z1) = self.bounds;
        let span_x = (x1 - x0 + 1) as f64;
        let span_z = (z1 - z0 + 1) as f64;
        let w = (r.right - r.left).max(1) as f64;
        let h = (r.bottom - r.top).max(1) as f64;
        let s = (span_x / w).max(span_z / h);
        let ox = r.left as f64;
        let oy = r.top as f64 + (h - span_z / s) / 2.0;
        (s, ox, oy)
    }

    fn cell_at(&self, px: i32, py: i32) -> Option<(usize, usize)> {
        let r = self.map_rect();
        let (s, ox, oy) = self.viewport(r);
        let (x0, _, x1, z1) = self.bounds;
        let gx = x0 as f64 + (px as f64 - ox) * s;
        let gz = z1 as f64 - (py as f64 - oy) * s;
        if gx < x0 as f64 || gx > x1 as f64 || gz < self.bounds.1 as f64 || gz > z1 as f64 {
            return None;
        }
        Some((gx as usize, gz as usize))
    }

    fn region_at(&self, px: i32, py: i32) -> Option<u8> {
        let grid = self.grid.as_ref()?;
        let (gx, gz) = self.cell_at(px, py)?;
        let id = grid.regions[gz * MAP_GRID + gx];
        (id != 0).then_some(id)
    }

    fn build_cache(&self, w: i32, h: i32) -> Option<Cache> {
        let grid = self.grid.as_ref()?;
        let max_density = grid.density.iter().copied().max().unwrap_or(1).max(1) as f32;
        let ln_max = (1.0 + max_density).ln();
        let n = (w * h) as usize;
        let mut ids = vec![0u8; n];
        let mut density = vec![0f32; n];
        for py in 0..h {
            for px in 0..w {
                if let Some((gx, gz)) = self.cell_at(px, py) {
                    let i = (py * w + px) as usize;
                    ids[i] = grid.regions[gz * MAP_GRID + gx];
                    let d = grid.density[(gz / 2) * DENSITY_GRID + gx / 2] as f32;
                    density[i] = (1.0 + d).ln() / ln_max;
                }
            }
        }
        let mut border = vec![false; n];
        for py in 0..h {
            for px in 0..w {
                let i = (py * w + px) as usize;
                let id = ids[i];
                let differs = |qx: i32, qy: i32| {
                    qx >= 0 && qy >= 0 && qx < w && qy < h && ids[(qy * w + qx) as usize] != id
                };
                border[i] = id != 0 && (differs(px + 1, py) || differs(px, py + 1) || differs(px - 1, py) || differs(px, py - 1));
            }
        }
        Some(Cache { w, h, ids, density, border })
    }

    fn values(&self) -> (Vec<f64>, f64) {
        let v: Vec<f64> = self.regions.iter().map(|r| r.as_ref().map_or(0.0, |r| r.p[self.kind])).collect();
        let max = v.iter().copied().fold(0.0, f64::max);
        (v, max)
    }

    fn shade(&self, cache: &Cache, pixels: &mut [u32]) {
        let (values, max) = self.values();
        let mut colour = [Rgb(0, 0, 0); REGIONS];
        for (id, c) in colour.iter_mut().enumerate().skip(1) {
            let t = if max > 0.0 { (values[id] / max).sqrt() } else { 0.0 };
            let mut base = gradient(t);
            if Some(id as u8) == self.hover {
                base = lerp(base, Rgb(255, 255, 255), 0.18);
            }
            if Some(id as u8) == self.selected {
                base = lerp(base, MAP_SELECTED, 0.35);
            }
            *c = base;
        }
        for (i, p) in pixels.iter_mut().enumerate() {
            let id = cache.ids[i] as usize;
            let d = cache.density[i] as f64;
            let rgb = if id == 0 {
                lerp(MAP_SPACE, MAP_STARS, d.powf(1.4))
            } else if cache.border[i] {
                if Some(id as u8) == self.selected { MAP_SELECTED } else { MAP_BORDER }
            } else {
                scale(colour[id], 0.45 + 0.55 * d)
            };
            *p = dib(rgb);
        }
    }

    fn info(&self) -> String {
        let kind = &KINDS[self.kind];
        match self.hover.or(self.selected).and_then(|id| self.regions[id as usize].as_ref()) {
            Some(r) => format!(
                "{}  \u{2014}  {} {}  \u{00B7}  {} predicted systems",
                r.name,
                thousands(r.p[self.kind], 0),
                kind.name,
                thousands_i(r.systems)
            ),
            None => format!("{} expected per region  \u{00B7}  click a region for its best sectors", kind.title()),
        }
    }

    fn caption(&self) -> String {
        let kind = KINDS[self.kind].name;
        match self.selected.and_then(|id| self.regions[id as usize].as_ref()) {
            Some(r) => format!("Top 10 sectors in {} by expected {}", r.name, kind),
            None => "Click a region on the map to list its top 10 sectors".to_string(),
        }
    }

    fn paint(&mut self) {
        let mut client = RECT::default();
        unsafe {
            let _ = GetClientRect(self.hwnd, &mut client);
        }
        let (w, h) = (client.right.max(1), client.bottom.max(1));
        if self.cache.as_ref().is_none_or(|c| c.w != w || c.h != h) {
            self.cache = self.build_cache(w, h);
        }
        unsafe {
            let mut ps = PAINTSTRUCT::default();
            let hdc = BeginPaint(self.hwnd, &mut ps);
            let mem = CreateCompatibleDC(Some(hdc));
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
                let old = SelectObject(mem, HGDIOBJ(bmp.0));
                let pixels = std::slice::from_raw_parts_mut(bits as *mut u32, (w * h) as usize);
                match &self.cache {
                    Some(cache) => self.shade(cache, pixels),
                    None => pixels.fill(dib(MAP_SPACE)),
                }
                let _ = GdiFlush();
                self.overlay_text(mem, client);
                let _ = BitBlt(hdc, 0, 0, w, h, Some(mem), 0, 0, SRCCOPY);
                SelectObject(mem, old);
                let _ = DeleteObject(HGDIOBJ(bmp.0));
            }
            let _ = DeleteDC(mem);
            let _ = EndPaint(self.hwnd, &ps);
        }
    }

    fn overlay_text(&self, dc: HDC, client: RECT) {
        unsafe { SetBkMode(dc, TRANSPARENT) };
        let top = RECT { bottom: self.layout.top, ..client };
        fill(dc, top, TABLE_ROW);
        fill(dc, RECT { top: top.bottom - 1, ..top }, HEADER_LINE);
        draw_text(dc, self.font, RECT { left: self.layout.info_left, ..top }, &self.info(), HEADER_TEXT, false);
        let side = RECT { left: client.right - self.layout.right, ..client };
        fill(dc, RECT { top: top.bottom, ..side }, TABLE_ROW);
        let caption = RECT { left: side.left + 6, top: top.bottom + 4, bottom: top.bottom + self.layout.caption, ..side };
        draw_wrapped(dc, self.font, caption, &self.caption(), HEADER_TEXT);
        if self.grid.is_none() {
            draw_text(dc, self.font, self.map_rect(), "loading the galaxy\u{2026}", TABLE_TEXT, true);
            return;
        }
        let r = self.map_rect();
        let (s, ox, oy) = self.viewport(r);
        let (x0, _, _, z1) = self.bounds;
        let mut order: Vec<&Region> = self.regions.iter().flatten().filter(|r| !r.name.is_empty()).collect();
        order.sort_by(|a, b| b.p[self.kind].total_cmp(&a.p[self.kind]));
        let mut placed: Vec<RECT> = Vec::new();
        for region in order {
            let px = (ox + (region.centre.0 - x0 as f64) / s) as i32;
            let py = (oy + (z1 as f64 - region.centre.1) / s) as i32;
            let half = text_width(dc, self.small, &region.name) / 2 + 2;
            let label = RECT { left: px - half, right: px + half, top: py - 8, bottom: py + 8 };
            let overlaps = |o: &RECT| label.left < o.right && o.left < label.right && label.top < o.bottom && o.top < label.bottom;
            if placed.iter().any(overlaps) {
                continue;
            }
            draw_text(dc, self.small, label, &region.name, MAP_LABEL, true);
            placed.push(label);
        }
        let (_, max) = self.values();
        let bar_w = 160.min((r.right - r.left) / 3);
        let bar = RECT { left: r.left + 10, right: r.left + 10 + bar_w, top: r.bottom - 22, bottom: r.bottom - 14 };
        for i in 0..bar_w {
            let c = gradient((i as f64 / bar_w as f64).max(0.0));
            fill(dc, RECT { left: bar.left + i, right: bar.left + i + 1, ..bar }, c);
        }
        draw_text(dc, self.small, RECT { left: bar.left, right: bar.left + 40, top: bar.top - 16, bottom: bar.top }, "0", MAP_LABEL, false);
        let max_label = thousands(max, 0);
        draw_text(
            dc,
            self.small,
            RECT { left: bar.right - 60, right: bar.right + 40, top: bar.top - 16, bottom: bar.top },
            &max_label,
            MAP_LABEL,
            false,
        );
    }

    fn mouse_move(&mut self, px: i32, py: i32) {
        if !self.tracking {
            let mut track = TRACKMOUSEEVENT {
                cbSize: std::mem::size_of::<TRACKMOUSEEVENT>() as u32,
                dwFlags: TME_LEAVE,
                hwndTrack: self.hwnd,
                dwHoverTime: 0,
            };
            unsafe {
                let _ = TrackMouseEvent(&mut track);
            }
            self.tracking = true;
        }
        let hover = self.region_at(px, py);
        if hover != self.hover {
            self.hover = hover;
            self.invalidate();
        }
    }

    fn mouse_leave(&mut self) {
        self.tracking = false;
        if self.hover.take().is_some() {
            self.invalidate();
        }
    }

    fn click(&mut self, px: i32, py: i32) -> Option<i64> {
        let id = self.region_at(px, py)?;
        self.selected = Some(id);
        self.invalidate();
        Some(id as i64)
    }
}

fn point(lparam: LPARAM) -> (i32, i32) {
    ((lparam.0 & 0xffff) as i16 as i32, ((lparam.0 >> 16) & 0xffff) as i16 as i32)
}

unsafe extern "system" fn wndproc(hwnd: HWND, msg: u32, wparam: WPARAM, lparam: LPARAM) -> LRESULT {
    match msg {
        WM_PAINT => {
            if main_window::with_map(|m| m.paint()).is_none() {
                return unsafe { DefWindowProcW(hwnd, msg, wparam, lparam) };
            }
            LRESULT(0)
        }
        WM_ERASEBKGND => LRESULT(1),
        WM_MOUSEMOVE => {
            let (x, y) = point(lparam);
            main_window::with_map(|m| m.mouse_move(x, y));
            LRESULT(0)
        }
        WM_MOUSELEAVE => {
            main_window::with_map(|m| m.mouse_leave());
            LRESULT(0)
        }
        WM_LBUTTONDOWN => {
            let (x, y) = point(lparam);
            if let Some(Some(region)) = main_window::with_map(|m| m.click(x, y)) {
                main_window::region_clicked(region);
            }
            LRESULT(0)
        }
        _ => unsafe { DefWindowProcW(hwnd, msg, wparam, lparam) },
    }
}
