use windows::Win32::Foundation::{HINSTANCE, HWND, LPARAM, LRESULT, RECT, SIZE, WPARAM};
use windows::Win32::Graphics::Gdi::{
    BI_RGB, BITMAPINFO, BITMAPINFOHEADER, BeginPaint, BitBlt, CreateCompatibleDC, CreateDIBSection, DIB_RGB_COLORS,
    DRAW_TEXT_FORMAT, DT_CENTER, DT_LEFT, DT_NOPREFIX, DT_RIGHT, DT_SINGLELINE, DT_VCENTER, DT_WORDBREAK, DeleteDC, DeleteObject, DrawTextW, EndPaint,
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
    HEADER_LINE, HEADER_TEXT, MAP_BORDER, MAP_CONFIRMED, MAP_FADE, MAP_GRADIENT, MAP_LABEL, MAP_SELECTED, MAP_SPACE, MAP_STARS,
    MAP_ZERO, Rgb,
    TABLE_ROW, TABLE_TEXT,
};

use super::expected_table::{colorref, fill};
use super::main_window;

const REGIONS: usize = 256;
const MARGIN_CELLS: usize = 24;
const LEGEND_WIDTH: i32 = 240;
const FOCUS_PIXELS: f64 = 50.0;
const FOCUS_EDGE: i32 = 2;
const DOT: i32 = 1;
const LY_PER_CELL: f64 = 4096.0 / 83.0;
const SECTOR_PROMPT: &str = "Type a sector name in the box above and pick it from the list";

pub struct MapLayout {
    pub top: i32,
    pub right: i32,
    pub caption: i32,
    pub info_left: i32,
    pub info_right: i32,
}

pub struct Focus {
    pub name: String,
    pub caption: String,
    pub cells: (f64, f64, f64, f64),
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
    catalogued: bool,
    selected: Option<u8>,
    hover: Option<u8>,
    cache: Option<Cache>,
    font: HFONT,
    small: HFONT,
    layout: MapLayout,
    tracking: bool,
    top_n: usize,
    sector_view: bool,
    focus: Option<Focus>,
    confirmed: Vec<(usize, f64, f64)>,
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

pub(super) fn text_width(dc: HDC, font: HFONT, s: &str) -> i32 {
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

pub(super) fn draw_aligned(dc: HDC, font: HFONT, r: RECT, s: &str, c: Rgb, align: DRAW_TEXT_FORMAT) {
    let mut t: Vec<u16> = s.encode_utf16().collect();
    let mut r = r;
    unsafe {
        let old = SelectObject(dc, HGDIOBJ(font.0));
        SetTextColor(dc, colorref(c));
        DrawTextW(dc, &mut t, &mut r, DT_SINGLELINE | DT_NOPREFIX | align);
        SelectObject(dc, old);
    }
}

pub(super) fn draw_text(dc: HDC, font: HFONT, r: RECT, s: &str, c: Rgb, centre: bool) {
    if s.is_empty() {
        return;
    }
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
    pub fn create(parent: HWND, instance: HINSTANCE, sector_view: bool) -> Result<MapView, String> {
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
                catalogued: false,
                selected: None,
                hover: None,
                cache: None,
                font: HFONT::default(),
                small: HFONT::default(),
                layout: MapLayout { top: 0, right: 0, caption: 0, info_left: 0, info_right: 0 },
                tracking: false,
                top_n: 10,
                sector_view,
                focus: None,
                confirmed: Vec::new(),
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
        self.fit_focus();
        self.cache = None;
        self.invalidate();
    }

    pub fn set_top(&mut self, n: usize) {
        self.top_n = n;
        self.invalidate();
    }

    pub fn set_kind(&mut self, kind: usize) {
        self.kind = kind;
        self.invalidate();
    }

    pub fn set_catalogued(&mut self, catalogued: bool) {
        self.catalogued = catalogued;
        self.invalidate();
    }

    pub fn set_focus(&mut self, focus: Focus) {
        self.focus = Some(focus);
        self.fit_focus();
        self.cache = None;
        self.invalidate();
    }

    fn fit_focus(&mut self) {
        let Some(focus) = &self.focus else { return };
        let (x0, z0, x1, z1) = focus.cells;
        let r = self.map_rect();
        let s = (x1 - x0).max(z1 - z0) / FOCUS_PIXELS;
        let half_x = (r.right - r.left).max(1) as f64 * s / 2.0;
        let half_z = (r.bottom - r.top).max(1) as f64 * s / 2.0;
        let (cx, cz) = ((x0 + x1) / 2.0, (z0 + z1) / 2.0);
        let last = (MAP_GRID - 1) as f64;
        let clamp = |v: f64| v.round().clamp(0.0, last) as usize;
        self.bounds = (clamp(cx - half_x), clamp(cz - half_z), clamp(cx + half_x), clamp(cz + half_z));
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
        if x1 >= x0 && self.focus.is_none() {
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

    pub fn show_confirmed(&mut self, kinds: &[String], pts: &[[f64; 3]]) {
        self.confirmed = kinds
            .iter()
            .zip(pts)
            .filter_map(|(k, p)| {
                let kind = KINDS.iter().position(|d| d.key == k)?;
                Some((kind, (p[0] + 49985.0) / LY_PER_CELL, (p[2] + 24105.0) / LY_PER_CELL))
            })
            .collect();
        self.invalidate();
    }

    fn draw_confirmed(&self, dc: HDC, r: RECT) -> usize {
        let (s, ox, oy) = self.viewport(r);
        let (x0, _, _, z1) = self.bounds;
        let mut shown = 0;
        for &(kind, cx, cz) in &self.confirmed {
            if kind != self.kind {
                continue;
            }
            shown += 1;
            let px = (ox + (cx - x0 as f64) / s) as i32;
            let py = (oy + (z1 as f64 - cz) / s) as i32;
            if px < r.left || px >= r.right || py < r.top || py >= r.bottom {
                continue;
            }
            let rim = DOT + 1;
            fill(dc, RECT { left: px - rim, right: px + rim + 1, top: py - rim, bottom: py + rim + 1 }, MAP_SPACE);
            fill(dc, RECT { left: px - DOT, right: px + DOT + 1, top: py - DOT, bottom: py + DOT + 1 }, MAP_CONFIRMED);
        }
        shown
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
        let ox = if self.focus.is_some() { r.left as f64 + (w - span_x / s) / 2.0 } else { r.left as f64 };
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
        let mut opacity = [0f64; REGIONS];
        for (id, c) in colour.iter_mut().enumerate().skip(1) {
            let t = if max > 0.0 { (values[id] / max).sqrt() } else { 0.0 };
            opacity[id] = if self.sector_view || values[id] < MAP_ZERO { 0.0 } else { (t / MAP_FADE).min(1.0) };
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
            let space = lerp(MAP_SPACE, MAP_STARS, d.powf(1.4));
            let rgb = if id == 0 {
                space
            } else if cache.border[i] {
                if Some(id as u8) == self.selected { MAP_SELECTED } else { MAP_BORDER }
            } else {
                lerp(space, scale(colour[id], 0.45 + 0.55 * d), opacity[id])
            };
            *p = dib(rgb);
        }
    }

    fn pointed(&self) -> Option<&Region> {
        self.hover.or(self.selected).and_then(|id| self.regions[id as usize].as_ref())
    }

    fn info(&self) -> String {
        self.pointed().map_or(String::new(), |r| r.name.clone())
    }

    fn caption(&self) -> String {
        if self.sector_view {
            return self.focus.as_ref().map_or(SECTOR_PROMPT.to_string(), |f| f.caption.clone());
        }
        let kind = KINDS[self.kind].name;
        match self.selected.and_then(|id| self.regions[id as usize].as_ref()) {
            Some(r) => format!("Top {} sectors in {} by expected {}", self.top_n, r.name, kind),
            None => format!("Click a region on the map to list its top {} sectors", self.top_n),
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
        let info = RECT { left: self.layout.info_left, right: client.right - self.layout.info_right, ..top };
        draw_text(dc, self.font, info, &self.info(), HEADER_TEXT, false);
        let side = RECT { left: client.right - self.layout.right, ..client };
        fill(dc, RECT { top: top.bottom, ..side }, TABLE_ROW);
        let caption = RECT { left: side.left + 6, top: top.bottom + 4, bottom: top.bottom + self.layout.caption, ..side };
        draw_wrapped(dc, self.font, caption, &self.caption(), HEADER_TEXT);
        if self.grid.is_none() {
            draw_text(dc, self.font, self.map_rect(), "loading the galaxy\u{2026}", TABLE_TEXT, true);
            return;
        }
        let r = self.map_rect();
        let shown = if self.sector_view { 0 } else { self.draw_confirmed(dc, r) };
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
        if self.sector_view {
            self.draw_focus(dc, r);
            return;
        }
        let (_, max) = self.values();
        let bar_w = LEGEND_WIDTH.min((r.right - r.left) / 3);
        let bar = RECT { left: r.left + 10, right: r.left + 10 + bar_w, top: r.bottom - 30, bottom: r.bottom - 20 };
        for i in 0..bar_w {
            let t = i as f64 / bar_w as f64;
            let c = lerp(MAP_SPACE, gradient(t), (t / MAP_FADE).min(1.0));
            fill(dc, RECT { left: bar.left + i, right: bar.left + i + 1, ..bar }, c);
        }
        let marks = [(0.0, DT_LEFT), (0.5, DT_CENTER), (1.0, DT_RIGHT)];
        for (t, align) in marks {
            let x = bar.left + ((bar_w - 1) as f64 * t) as i32;
            fill(dc, RECT { left: x, right: x + 1, top: bar.bottom, bottom: bar.bottom + 4 }, MAP_LABEL);
            let value = thousands(max * t * t, 0);
            let label = match align {
                DT_LEFT => RECT { left: x, right: x + 80, top: bar.bottom + 4, bottom: bar.bottom + 18 },
                DT_RIGHT => RECT { left: x - 80, right: x + 1, top: bar.bottom + 4, bottom: bar.bottom + 18 },
                _ => RECT { left: x - 40, right: x + 40, top: bar.bottom + 4, bottom: bar.bottom + 18 },
            };
            draw_aligned(dc, self.small, label, &value, MAP_LABEL, align);
        }
        let pool = if self.catalogued { "boxel-predicted and plot only" } else { "boxel-predicted only" };
        let caption = format!("expected {} per region, {pool}", KINDS[self.kind].name);
        draw_text(dc, self.small, RECT { left: bar.left, right: bar.left + 300, top: bar.top - 16, bottom: bar.top }, &caption, MAP_LABEL, false);
        let found = format!("{} confirmed {} not yet visited", thousands_i(shown as i64), KINDS[self.kind].name);
        let key = RECT { left: bar.left, right: bar.left + 300, top: bar.top - 32, bottom: bar.top - 16 };
        fill(dc, RECT { left: key.left + 2 - DOT, right: key.left + 3 + DOT, top: (key.top + key.bottom) / 2 - DOT, bottom: (key.top + key.bottom) / 2 + DOT + 1 }, MAP_CONFIRMED);
        draw_text(dc, self.small, RECT { left: key.left + 10, ..key }, &found, MAP_CONFIRMED, false);
        if let Some(region) = self.pointed() {
            let systems = format!("{} predicted systems", thousands_i(region.systems));
            let at = RECT { left: bar.right + 10, right: r.right - 10, top: bar.top - 4, bottom: bar.bottom + 4 };
            draw_aligned(dc, self.small, at, &systems, MAP_LABEL, DT_RIGHT | DT_VCENTER);
        }
    }

    fn draw_focus(&self, dc: HDC, r: RECT) {
        let Some(focus) = &self.focus else { return };
        let (s, ox, oy) = self.viewport(r);
        let (x0, _, _, z1) = self.bounds;
        let (fx0, fz0, fx1, fz1) = focus.cells;
        let left = (ox + (fx0 - x0 as f64) / s) as i32;
        let right = (ox + (fx1 - x0 as f64) / s) as i32;
        let top = (oy + (z1 as f64 - fz1) / s) as i32;
        let bottom = (oy + (z1 as f64 - fz0) / s) as i32;
        let frame = RECT { left, top, right, bottom };
        for edge in [
            RECT { bottom: top + FOCUS_EDGE, ..frame },
            RECT { top: bottom - FOCUS_EDGE, ..frame },
            RECT { right: left + FOCUS_EDGE, ..frame },
            RECT { left: right - FOCUS_EDGE, ..frame },
        ] {
            fill(dc, edge, MAP_SELECTED);
        }
        let half = text_width(dc, self.font, &focus.name) / 2 + 4;
        let centre = (left + right) / 2;
        let label = RECT { left: centre - half, right: centre + half, top: top - 22, bottom: top - 4 };
        draw_text(dc, self.font, label, &focus.name, MAP_SELECTED, true);
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
        if self.sector_view {
            return None;
        }
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
            if main_window::with_map(hwnd, |m| m.paint()).is_none() {
                return unsafe { DefWindowProcW(hwnd, msg, wparam, lparam) };
            }
            LRESULT(0)
        }
        WM_ERASEBKGND => LRESULT(1),
        WM_MOUSEMOVE => {
            let (x, y) = point(lparam);
            main_window::with_map(hwnd, |m| m.mouse_move(x, y));
            LRESULT(0)
        }
        WM_MOUSELEAVE => {
            main_window::with_map(hwnd, |m| m.mouse_leave());
            LRESULT(0)
        }
        WM_LBUTTONDOWN => {
            let (x, y) = point(lparam);
            if let Some(Some(region)) = main_window::with_map(hwnd, |m| m.click(x, y)) {
                main_window::region_clicked(region);
            }
            LRESULT(0)
        }
        _ => unsafe { DefWindowProcW(hwnd, msg, wparam, lparam) },
    }
}
