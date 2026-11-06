use std::collections::{BTreeSet, HashMap};
use std::ops::RangeInclusive;

use windows::Win32::Foundation::{HINSTANCE, HWND, LPARAM, LRESULT, RECT, SIZE, WPARAM};
use windows::Win32::Graphics::Gdi::{
    BI_RGB, BITMAPINFO, BITMAPINFOHEADER, BeginPaint, BitBlt, CLEARTYPE_QUALITY, CLIP_DEFAULT_PRECIS, CreateCompatibleDC, CreateDIBSection,
    CreateFontW, DEFAULT_CHARSET, DIB_RGB_COLORS, DRAW_TEXT_FORMAT, DT_CENTER, DT_END_ELLIPSIS, DT_LEFT, DT_NOPREFIX, DT_RIGHT, DT_SINGLELINE,
    DT_VCENTER, DeleteDC, DeleteObject, DrawTextW, EndPaint, FF_DONTCARE, FW_NORMAL, GdiFlush, GetTextExtentPoint32W, HDC, HFONT,
    HGDIOBJ, IntersectClipRect, InvalidateRect, OUT_DEFAULT_PRECIS, PAINTSTRUCT, SRCCOPY, SelectClipRgn, SelectObject, SetBkMode, SetTextColor, TRANSPARENT, VARIABLE_PITCH,
};
use windows::Win32::System::LibraryLoader::GetModuleHandleW;
use windows::Win32::UI::Controls::WM_MOUSELEAVE;
use windows::Win32::UI::Input::KeyboardAndMouse::{TME_LEAVE, TRACKMOUSEEVENT, TrackMouseEvent};
use windows::Win32::UI::WindowsAndMessaging::{
    CS_DBLCLKS, CreateWindowExW, DefWindowProcW, GetClientRect, IDC_ARROW, LoadCursorW, RegisterClassExW, WINDOW_EX_STYLE,
    WM_ERASEBKGND, WM_LBUTTONDBLCLK, WM_LBUTTONDOWN, WM_MOUSEMOVE, WM_PAINT, WM_RBUTTONUP, WNDCLASSEXW, WS_CHILD, WS_CLIPSIBLINGS,
};
use windows::core::{PCWSTR, w};

use crate::database::{DENSITY_GRID, MAP_GRID, MapGrid, REGION_CELL_LY, RegionExpected};
use crate::kinds::KINDS;
use crate::names::{SECTOR_LY, sector_cell};
use crate::table::{thousands, thousands_i};
use crate::theme::{
    HEADER_LINE, MAP_BORDER, MAP_CONFIRMED, MAP_FADE, MAP_GRADIENT, MAP_LABEL, MAP_SECTOR_EDGE, MAP_SECTOR_GRID,
    MAP_SECTOR_NAME, MAP_SECTOR_ALPHA, MAP_SECTOR_ZERO, MAP_SELECTED, MAP_SPACE, MAP_STARS, MAP_ZERO, Rgb, TABLE_ROW, TABLE_TEXT,
};

use super::expected_table::{colorref, fill};
use super::main_window;

const REGIONS: usize = 256;
const MARGIN_CELLS: usize = 24;
const ZOOM_MARGIN_COLUMNS: f64 = 0.5;
const LEGEND_LINE: i32 = 20;
const LEGEND_INSET: i32 = 2;
const LEGEND_BAR: i32 = 10;
const PICK_EDGE: i32 = 2;
const DOT: i32 = 1;
const LABEL_PAD: i32 = 4;
const LABEL_MIN_PERCENT: i32 = 75;
const LABEL_MAX_PERCENT: i32 = 160;
const LABEL_FACE: &str = "Segoe UI";
const EDGE_STEPS: [(i32, i32); 4] = [(0, -1), (-1, 0), (1, 0), (0, 1)];
const COLUMN_EPSILON: f64 = 1e-4;
const FOCUS_REACH: i64 = 1;
const FOCUS_MARGIN_COLUMNS: f64 = 1.0;

pub struct MapLayout {
    pub top: i32,
    pub right: i32,
    pub pad: i32,
    pub inset: i32,
}

pub enum MapClick {
    Region(i64),
    Zoom(i64),
    Sector(String),
    Square(Vec<RegionExpected>),
    ZoomOut,
    Unnamed,
}

struct Region {
    name: String,
    systems: i64,
    known: i64,
    p: [f64; KINDS.len()],
    conf: [i64; KINDS.len()],
    sectors: i64,
    centre: (f64, f64),
}

struct Zoom {
    region: u8,
    columns: Vec<(i64, i64)>,
    index: HashMap<(i64, i64), usize>,
    sectors: Vec<RegionExpected>,
    by_column: Vec<Vec<usize>>,
    loaded: bool,
    picked: Option<String>,
    outline: Option<(String, (f64, f64, f64, f64))>,
    hover: Option<usize>,
    galaxy: [f64; KINDS.len()],
    bounds: (usize, usize, usize, usize),
    focus: Option<(i64, i64)>,
    marked: Option<usize>,
}

impl Zoom {
    fn in_focus(&self, (x, z): (i64, i64)) -> bool {
        self.focus.is_some_and(|(fx, fz)| (x - fx).abs() <= FOCUS_REACH && (z - fz).abs() <= FOCUS_REACH)
    }

    fn focus_cells(&self) -> Vec<(i64, i64)> {
        let Some((fx, fz)) = self.focus else { return Vec::new() };
        (-FOCUS_REACH..=FOCUS_REACH).flat_map(|dz| (-FOCUS_REACH..=FOCUS_REACH).map(move |dx| (fx + dx, fz + dz))).collect()
    }

    fn lit_column(&self) -> Option<usize> {
        self.marked.or_else(|| self.picked_column())
    }

    fn picked_column(&self) -> Option<usize> {
        let picked = self.picked.as_deref()?;
        self.by_column.iter().position(|members| members.iter().any(|&i| self.sectors[i].region == picked))
    }

    fn value(&self, col: usize, kind: usize) -> f64 {
        self.by_column[col].iter().map(|&i| self.sectors[i].p[kind]).sum()
    }
}

struct Cache {
    w: i32,
    h: i32,
    ids: Vec<u8>,
    density: Vec<f32>,
    border: Vec<bool>,
    column: Vec<i32>,
}

struct Lines {
    first: i32,
    line: i32,
    shown: usize,
}

pub struct MapView {
    pub hwnd: HWND,
    grid: Option<Box<MapGrid>>,
    regions: Vec<Option<Region>>,
    bounds: (usize, usize, usize, usize),
    galaxy_bounds: (usize, usize, usize, usize),
    kind: usize,
    catalogued: bool,
    selected: Option<u8>,
    hover: Option<u8>,
    cache: Option<Cache>,
    font: HFONT,
    small: HFONT,
    layout: MapLayout,
    caption: (i32, i32),
    tracking: bool,
    zoom: Option<Zoom>,
    confirmed: Vec<(usize, f64, f64)>,
    label: (i32, HFONT),
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

fn column_span() -> f64 {
    SECTOR_LY / REGION_CELL_LY
}

fn column_range(cell: usize) -> RangeInclusive<i64> {
    let span = column_span();
    let lo = (cell as f64 / span).floor() as i64;
    let hi = ((cell as f64 + 1.0 - COLUMN_EPSILON) / span).floor() as i64;
    lo..=hi
}

fn column_bounds((cx0, cz0): (i64, i64), (cx1, cz1): (i64, i64), margin: f64) -> (usize, usize, usize, usize) {
    let span = column_span();
    let last = (MAP_GRID - 1) as f64;
    let lo = |c: i64| ((c as f64 - margin) * span).floor().clamp(0.0, last) as usize;
    let hi = |c: i64| ((c as f64 + 1.0 + margin) * span).ceil().clamp(0.0, last) as usize;
    (lo(cx0), lo(cz0), hi(cx1), hi(cz1))
}

fn region_columns(regions: &[u8], region: u8) -> Vec<(i64, i64)> {
    let mut set = BTreeSet::new();
    for z in 0..MAP_GRID {
        let row = &regions[z * MAP_GRID..(z + 1) * MAP_GRID];
        let mut x = 0;
        while x < MAP_GRID {
            if row[x] != region {
                x += 1;
                continue;
            }
            let start = x;
            while x < MAP_GRID && row[x] == region {
                x += 1;
            }
            let (from, to) = (*column_range(start).start(), *column_range(x - 1).end());
            for cz in column_range(z) {
                for cx in from..=to {
                    set.insert((cx, cz));
                }
            }
        }
    }
    set.into_iter().collect()
}

pub(super) fn text_width(dc: HDC, font: HFONT, s: &str) -> i32 {
    text_size(dc, font, s).cx
}

fn text_size(dc: HDC, font: HFONT, s: &str) -> SIZE {
    let t: Vec<u16> = s.encode_utf16().collect();
    let mut size = SIZE::default();
    unsafe {
        let old = SelectObject(dc, HGDIOBJ(font.0));
        let _ = GetTextExtentPoint32W(dc, &t, &mut size);
        SelectObject(dc, old);
    }
    size
}

pub(super) fn draw_aligned(dc: HDC, font: HFONT, r: RECT, s: &str, c: Rgb, align: DRAW_TEXT_FORMAT) {
    if s.is_empty() {
        return;
    }
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

fn label_font(line: i32) -> HFONT {
    let face: Vec<u16> = LABEL_FACE.encode_utf16().chain(Some(0)).collect();
    unsafe {
        CreateFontW(
            line,
            0,
            0,
            0,
            FW_NORMAL.0 as i32,
            0,
            0,
            0,
            DEFAULT_CHARSET,
            OUT_DEFAULT_PRECIS,
            CLIP_DEFAULT_PRECIS,
            CLEARTYPE_QUALITY,
            (VARIABLE_PITCH.0 | FF_DONTCARE.0) as u32,
            PCWSTR(face.as_ptr()),
        )
    }
}

fn draw_outlined(dc: HDC, font: HFONT, r: RECT, s: &str, c: Rgb) {
    let format = DT_SINGLELINE | DT_VCENTER | DT_CENTER | DT_NOPREFIX | DT_END_ELLIPSIS;
    for (dx, dy) in EDGE_STEPS {
        let at = RECT { left: r.left + dx, right: r.right + dx, top: r.top + dy, bottom: r.bottom + dy };
        draw_aligned(dc, font, at, s, MAP_SECTOR_EDGE, format);
    }
    draw_aligned(dc, font, r, s, c, format);
}

fn tone(v: f64, max: f64, zero: f64) -> (Rgb, f64) {
    let t = if max > 0.0 { (v / max).sqrt() } else { 0.0 };
    let opacity = if v < zero { 0.0 } else { (t / MAP_FADE).min(1.0) };
    (gradient(t), opacity)
}

fn outline(dc: HDC, r: RECT, edge: i32, c: Rgb) {
    for side in [
        RECT { bottom: r.top + edge, ..r },
        RECT { top: r.bottom - edge, ..r },
        RECT { right: r.left + edge, ..r },
        RECT { left: r.right - edge, ..r },
    ] {
        fill(dc, side, c);
    }
}

impl MapView {
    pub fn create(parent: HWND, instance: HINSTANCE) -> Result<MapView, String> {
        unsafe {
            let class = WNDCLASSEXW {
                cbSize: std::mem::size_of::<WNDCLASSEXW>() as u32,
                style: CS_DBLCLKS,
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
            let all = (0, 0, MAP_GRID - 1, MAP_GRID - 1);
            Ok(MapView {
                hwnd,
                grid: None,
                regions: (0..REGIONS).map(|_| None).collect(),
                bounds: all,
                galaxy_bounds: all,
                kind: 0,
                catalogued: false,
                selected: None,
                hover: None,
                cache: None,
                font: HFONT::default(),
                small: HFONT::default(),
                layout: MapLayout { top: 0, right: 0, pad: 0, inset: 0 },
                caption: (0, 0),
                tracking: false,
                zoom: None,
                confirmed: Vec::new(),
                label: (0, HFONT::default()),
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

    pub fn set_catalogued(&mut self, catalogued: bool) {
        self.catalogued = catalogued;
        self.invalidate();
    }

    pub fn kind(&self) -> usize {
        self.kind
    }

    pub fn selected_region(&self) -> Option<i64> {
        self.selected.map(i64::from)
    }

    pub fn set_caption(&mut self, top: i32, height: i32) {
        if (top, height) != self.caption {
            self.caption = (top, height);
            self.invalidate();
        }
    }

    fn caption_region(&self) -> Option<&Region> {
        let id = self.zoom.as_ref().map(|z| z.region).or(self.selected)?;
        self.regions[id as usize].as_ref().filter(|r| !r.name.is_empty())
    }

    pub fn zoomed_region(&self) -> Option<i64> {
        self.zoom.as_ref().map(|z| i64::from(z.region))
    }

    pub fn selected_total(&self) -> Option<RegionExpected> {
        let id = self.selected?;
        let r = self.regions[id as usize].as_ref()?;
        Some(RegionExpected { region: r.name.clone(), id: Some(id as i64), systems: r.systems, known: r.known, p: r.p, conf: r.conf, sectors: r.sectors })
    }

    pub fn region_at_cells(&self, u: f64, v: f64) -> Option<i64> {
        let grid = self.grid.as_ref()?;
        let last = (MAP_GRID - 1) as f64;
        let (x, z) = (u.floor().clamp(0.0, last) as usize, v.floor().clamp(0.0, last) as usize);
        let id = grid.regions[z * MAP_GRID + x];
        (id != 0).then_some(i64::from(id))
    }

    pub fn zoom_to(&mut self, region: i64) -> bool {
        let Ok(region) = u8::try_from(region) else { return false };
        let Some(grid) = self.grid.as_ref() else { return false };
        let columns = region_columns(&grid.regions, region);
        let (Some(cx0), Some(cx1)) = (columns.iter().map(|c| c.0).min(), columns.iter().map(|c| c.0).max()) else {
            return false;
        };
        let (cz0, cz1) = (columns.iter().map(|c| c.1).min().unwrap_or(0), columns.iter().map(|c| c.1).max().unwrap_or(0));
        let bounds = column_bounds((cx0, cz0), (cx1, cz1), ZOOM_MARGIN_COLUMNS);
        self.bounds = bounds;
        let index = columns.iter().enumerate().map(|(i, c)| (*c, i)).collect();
        let by_column = vec![Vec::new(); columns.len()];
        self.zoom = Some(Zoom {
            region,
            columns,
            index,
            sectors: Vec::new(),
            by_column,
            loaded: false,
            picked: None,
            outline: None,
            hover: None,
            galaxy: [0.0; KINDS.len()],
            bounds,
            focus: None,
            marked: None,
        });
        self.selected = Some(region);
        self.cache = None;
        self.invalidate();
        true
    }

    pub fn focus_on(&mut self, column: (i64, i64)) {
        let Some(zoom) = self.zoom.as_mut() else { return };
        zoom.focus = Some(column);
        let reach = (FOCUS_REACH, FOCUS_REACH);
        self.bounds = column_bounds((column.0 - reach.0, column.1 - reach.1), (column.0 + reach.0, column.1 + reach.1), FOCUS_MARGIN_COLUMNS);
        self.cache = None;
        self.invalidate();
    }

    fn focus_picked(&mut self) {
        let Some(zoom) = self.zoom.as_ref() else { return };
        if let Some(col) = zoom.picked_column().filter(|&c| !zoom.in_focus(zoom.columns[c])) {
            self.focus_on(zoom.columns[col]);
        }
    }

    pub fn zoom_out(&mut self) -> bool {
        if let Some(zoom) = self.zoom.as_mut().filter(|z| z.focus.is_some()) {
            zoom.focus = None;
            self.bounds = zoom.bounds;
            self.cache = None;
            self.invalidate();
            return true;
        }
        if self.zoom.take().is_none() {
            return false;
        }
        self.bounds = self.galaxy_bounds;
        self.cache = None;
        self.invalidate();
        true
    }

    pub fn show_region_sectors(&mut self, region: i64, rows: Vec<RegionExpected>, galaxy: [f64; KINDS.len()]) {
        let Some(zoom) = self.zoom.as_mut().filter(|z| i64::from(z.region) == region) else { return };
        let mut by_column = vec![Vec::new(); zoom.columns.len()];
        for (i, row) in rows.iter().enumerate() {
            let Some(id) = row.id else { continue };
            let [x, _, z] = sector_cell(id);
            if let Some(&col) = zoom.index.get(&(x, z)) {
                by_column[col].push(i);
            }
        }
        for members in &mut by_column {
            members.sort_by_key(|&i| std::cmp::Reverse(rows[i].id.map(|id| sector_cell(id)[1])));
        }
        zoom.sectors = rows;
        zoom.by_column = by_column;
        zoom.galaxy = galaxy;
        zoom.loaded = true;
        self.focus_picked();
        self.invalidate();
    }

    pub fn pick_sector(&mut self, name: &str, crafted_box: Option<(f64, f64, f64, f64)>) {
        let Some(zoom) = self.zoom.as_mut() else { return };
        zoom.picked = Some(name.to_string());
        zoom.marked = None;
        zoom.outline = crafted_box.map(|b| (name.to_string(), b));
        self.focus_picked();
        self.invalidate();
    }

    pub fn picked_sector(&self) -> Option<String> {
        self.zoom.as_ref()?.picked.clone()
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
            self.galaxy_bounds = (
                x0.saturating_sub(MARGIN_CELLS),
                z0.saturating_sub(MARGIN_CELLS),
                (x1 + MARGIN_CELLS).min(MAP_GRID - 1),
                (z1 + MARGIN_CELLS).min(MAP_GRID - 1),
            );
            if self.zoom.is_none() {
                self.bounds = self.galaxy_bounds;
            }
        }
        for (id, s) in sums.iter().enumerate() {
            if s.2 > 0.0 {
                let r = self.regions[id].get_or_insert_with(Self::empty_region);
                r.centre = (s.0 / s.2, s.1 / s.2);
            }
        }
        self.grid = Some(Box::new(grid));
        self.cache = None;
        self.invalidate();
    }

    fn empty_region() -> Region {
        Region { name: String::new(), systems: 0, known: 0, p: [0.0; KINDS.len()], conf: [0; KINDS.len()], sectors: 0, centre: (0.0, 0.0) }
    }

    pub fn show_regions(&mut self, rows: &[RegionExpected]) {
        for row in rows {
            let Some(id) = row.id.filter(|&i| (1..REGIONS as i64).contains(&i)) else { continue };
            let r = self.regions[id as usize].get_or_insert_with(Self::empty_region);
            r.name = row.region.clone();
            r.systems = row.systems;
            r.known = row.known;
            r.p = row.p;
            r.conf = row.conf;
            r.sectors = row.sectors;
        }
        self.invalidate();
    }

    pub fn show_confirmed(&mut self, kinds: &[String], pts: &[[f64; 3]]) {
        self.confirmed = kinds
            .iter()
            .zip(pts)
            .filter_map(|(k, p)| {
                let kind = KINDS.iter().position(|d| d.key == k)?;
                Some((kind, (p[0] + 49985.0) / REGION_CELL_LY, (p[2] + 24105.0) / REGION_CELL_LY))
            })
            .collect();
        self.invalidate();
    }

    fn draw_confirmed(&self, dc: HDC, r: RECT) {
        for &(kind, cx, cz) in &self.confirmed {
            if kind != self.kind {
                continue;
            }
            let (px, py) = self.to_px(r, cx, cz);
            let (px, py) = (px as i32, py as i32);
            if px < r.left || px >= r.right || py < r.top || py >= r.bottom {
                continue;
            }
            let rim = DOT + 1;
            fill(dc, RECT { left: px - rim, right: px + rim + 1, top: py - rim, bottom: py + rim + 1 }, MAP_SPACE);
            fill(dc, RECT { left: px - DOT, right: px + DOT + 1, top: py - DOT, bottom: py + DOT + 1 }, MAP_CONFIRMED);
        }
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
        let r = RECT { top: r.top + self.layout.inset, ..r };
        let (x0, z0, x1, z1) = self.bounds;
        let span_x = (x1 - x0 + 1) as f64;
        let span_z = (z1 - z0 + 1) as f64;
        let w = (r.right - r.left).max(1) as f64;
        let h = (r.bottom - r.top).max(1) as f64;
        let s = (span_x / w).max(span_z / h);
        let ox = if self.zoom.is_some() { r.left as f64 + (w - span_x / s) / 2.0 } else { r.left as f64 };
        let oy = r.top as f64 + (h - span_z / s) / 2.0;
        (s, ox, oy)
    }

    fn to_px(&self, r: RECT, u: f64, v: f64) -> (f64, f64) {
        let (s, ox, oy) = self.viewport(r);
        let (x0, _, _, z1) = self.bounds;
        (ox + (u - x0 as f64) / s, oy + (z1 as f64 - v) / s)
    }

    fn grid_at(&self, r: RECT, px: i32, py: i32) -> Option<(f64, f64)> {
        if px < r.left || px >= r.right || py < r.top || py >= r.bottom {
            return None;
        }
        let (s, ox, oy) = self.viewport(r);
        let (x0, _, _, z1) = self.bounds;
        let u = x0 as f64 + (px as f64 - ox) * s;
        let v = z1 as f64 - (py as f64 - oy) * s;
        let edge = MAP_GRID as f64;
        if u < 0.0 || u >= edge || v < 0.0 || v >= edge {
            return None;
        }
        Some((u, v))
    }

    fn region_at(&self, px: i32, py: i32) -> Option<u8> {
        let grid = self.grid.as_ref()?;
        let (u, v) = self.grid_at(self.map_rect(), px, py)?;
        let id = grid.regions[v as usize * MAP_GRID + u as usize];
        (id != 0).then_some(id)
    }

    fn column_of(zoom: &Zoom, u: f64, v: f64) -> Option<usize> {
        let span = column_span();
        zoom.index.get(&((u / span).floor() as i64, (v / span).floor() as i64)).copied()
    }

    fn column_at(&self, px: i32, py: i32) -> Option<usize> {
        let zoom = self.zoom.as_ref()?;
        let (u, v) = self.grid_at(self.map_rect(), px, py)?;
        Self::column_of(zoom, u, v)
    }

    fn column_rect(&self, r: RECT, (cx, cz): (i64, i64)) -> RECT {
        let span = column_span();
        let (left, top) = self.to_px(r, cx as f64 * span, (cz + 1) as f64 * span);
        let (right, bottom) = self.to_px(r, (cx + 1) as f64 * span, cz as f64 * span);
        RECT { left: left.round() as i32, top: top.round() as i32, right: right.round() as i32, bottom: bottom.round() as i32 }
    }

    fn build_cache(&self, w: i32, h: i32) -> Option<Cache> {
        let grid = self.grid.as_ref()?;
        let r = self.map_rect();
        let max_density = grid.density.iter().copied().max().unwrap_or(1).max(1) as f32;
        let ln_max = (1.0 + max_density).ln();
        let n = (w * h) as usize;
        let mut ids = vec![0u8; n];
        let mut density = vec![0f32; n];
        let mut column = vec![-1i32; n];
        for py in 0..h {
            for px in 0..w {
                if let Some((u, v)) = self.grid_at(r, px, py) {
                    let (gx, gz) = (u as usize, v as usize);
                    let i = (py * w + px) as usize;
                    ids[i] = grid.regions[gz * MAP_GRID + gx];
                    let d = grid.density[(gz / 2) * DENSITY_GRID + gx / 2] as f32;
                    density[i] = (1.0 + d).ln() / ln_max;
                    if let Some(zoom) = &self.zoom {
                        column[i] = Self::column_of(zoom, u, v).map_or(-1, |c| c as i32);
                    }
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
        Some(Cache { w, h, ids, density, border, column })
    }

    fn values(&self) -> (Vec<f64>, f64) {
        let v: Vec<f64> = match &self.zoom {
            Some(zoom) => (0..zoom.columns.len()).map(|c| zoom.value(c, self.kind)).collect(),
            None => self.regions.iter().map(|r| r.as_ref().map_or(0.0, |r| r.p[self.kind])).collect(),
        };
        let local = v.iter().copied().fold(0.0, f64::max);
        let max = self.zoom.as_ref().map_or(local, |z| z.galaxy[self.kind].max(local));
        (v, max)
    }

    fn palette(&self, values: &[f64], max: f64, zero: f64, hover: Option<usize>, selected: Option<usize>) -> Vec<(Rgb, f64)> {
        values
            .iter()
            .enumerate()
            .map(|(i, &v)| {
                let (base, opacity) = tone(v, max, zero);
                (Self::tint(base, Some(i), hover, selected), opacity)
            })
            .collect()
    }

    fn tint(base: Rgb, at: Option<usize>, hover: Option<usize>, selected: Option<usize>) -> Rgb {
        let mut base = base;
        if at.is_some() && at == hover {
            base = lerp(base, Rgb(255, 255, 255), 0.18);
        }
        if at.is_some() && at == selected {
            base = lerp(base, MAP_SELECTED, 0.35);
        }
        base
    }

    fn shade(&self, cache: &Cache, pixels: &mut [u32]) {
        let (values, max) = self.values();
        let colours = match &self.zoom {
            Some(_) => Vec::new(),
            None => self.palette(&values, max, MAP_ZERO, self.hover.map(usize::from), self.selected.map(usize::from)),
        };
        let picked = self.zoom.as_ref().and_then(Zoom::lit_column);
        for (i, p) in pixels.iter_mut().enumerate() {
            let id = cache.ids[i];
            let d = cache.density[i] as f64;
            let space = lerp(MAP_SPACE, MAP_STARS, d.powf(1.4));
            let toned = match &self.zoom {
                Some(zoom) => usize::try_from(cache.column[i]).ok().filter(|&col| zoom.focus.is_none() || zoom.in_focus(zoom.columns[col])).map(|col| {
                    let (base, opacity) = tone(values[col], max, MAP_SECTOR_ZERO);
                    (Self::tint(base, Some(col), zoom.hover, picked), opacity)
                }),
                None => (id != 0).then(|| colours.get(id as usize).copied()).flatten(),
            };
            let rgb = if cache.border[i] {
                if Some(id) == self.selected { MAP_SELECTED } else { MAP_BORDER }
            } else if let Some((colour, opacity)) = toned {
                match self.zoom {
                    Some(_) => lerp(space, colour, opacity * MAP_SECTOR_ALPHA),
                    None => lerp(space, scale(colour, 0.45 + 0.55 * d), opacity),
                }
            } else {
                space
            };
            *p = dib(rgb);
        }
    }

    fn column_names(zoom: &Zoom, col: usize) -> Vec<&str> {
        zoom.by_column[col].iter().map(|&i| zoom.sectors[i].region.as_str()).collect()
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
            self.fit_labels(hdc);
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
        let side = RECT { left: client.right - self.layout.right, ..client };
        fill(dc, RECT { top: top.bottom, ..side }, TABLE_ROW);
        if self.grid.is_none() {
            draw_text(dc, self.font, self.map_rect(), "loading the galaxy\u{2026}", TABLE_TEXT, true);
            return;
        }
        let r = self.map_rect();
        self.draw_confirmed(dc, r);
        match &self.zoom {
            Some(zoom) => self.draw_sectors(dc, r, zoom),
            None => self.draw_region_labels(dc, r),
        }
        let panel = RECT { left: side.left + self.layout.pad, right: client.right - LEGEND_INSET, top: client.top, bottom: client.bottom - self.layout.pad };
        if let Some(region) = self.caption_region() {
            let (top, line) = self.caption;
            let name = RECT { left: client.right - self.layout.right + self.layout.pad, right: client.right, top, bottom: top + line };
            draw_aligned(dc, self.font, name, &region.name, MAP_LABEL, DT_LEFT | DT_VCENTER);
            let count = RECT { top: name.bottom, bottom: name.bottom + line, ..name };
            draw_aligned(dc, self.font, count, &format!("{} sectors", thousands_i(region.sectors)), MAP_LABEL, DT_LEFT | DT_VCENTER);
        }
        self.draw_legend(dc, panel);
    }

    fn draw_region_labels(&self, dc: HDC, r: RECT) {
        let mut order: Vec<&Region> = self.regions.iter().flatten().filter(|r| !r.name.is_empty()).collect();
        order.sort_by(|a, b| b.p[self.kind].total_cmp(&a.p[self.kind]));
        let mut placed: Vec<RECT> = Vec::new();
        for region in order {
            let (px, py) = self.to_px(r, region.centre.0, region.centre.1);
            let (px, py) = (px as i32, py as i32);
            let half = text_width(dc, self.small, &region.name) / 2 + 2;
            let label = RECT { left: px - half, right: px + half, top: py - 8, bottom: py + 8 };
            let overlaps = |o: &RECT| label.left < o.right && o.left < label.right && label.top < o.bottom && o.top < label.bottom;
            if placed.iter().any(overlaps) {
                continue;
            }
            draw_text(dc, self.small, label, &region.name, MAP_LABEL, true);
            placed.push(label);
        }
    }

    fn fit_labels(&mut self, dc: HDC) {
        let Some(zoom) = &self.zoom else { return };
        let Some(centre) = zoom.focus else { return };
        let r = self.map_rect();
        let cell = self.column_rect(r, centre);
        let cell_h = cell.bottom - cell.top;
        let most = zoom.focus_cells().iter().filter_map(|c| zoom.index.get(c)).map(|&i| zoom.by_column[i].len()).max().unwrap_or(1).max(1) as i32;
        let full = text_size(dc, self.small, "Ag").cy.max(1);
        let line = ((cell_h - LABEL_PAD) / most).clamp(full * LABEL_MIN_PERCENT / 100, full * LABEL_MAX_PERCENT / 100).max(1);
        if line != self.label.0 {
            if !self.label.1.is_invalid() {
                unsafe {
                    let _ = DeleteObject(HGDIOBJ(self.label.1.0));
                }
            }
            self.label = (line, label_font(line));
        }
    }

    fn lines(&self, cell: RECT, n: usize) -> Lines {
        let line = self.label.0.max(1);
        let fit = ((cell.bottom - cell.top - LABEL_PAD) / line).max(0) as usize;
        let shown = n.min(fit);
        Lines { first: cell.top + (cell.bottom - cell.top - shown as i32 * line) / 2, line, shown }
    }

    fn labels(zoom: &Zoom, col: usize, shown: usize) -> Vec<(String, bool)> {
        let names = Self::column_names(zoom, col);
        let lit = |n: &str| Some(n) == zoom.picked.as_deref();
        if shown >= names.len() {
            return names.iter().map(|n| (n.to_string(), lit(n))).collect();
        }
        if shown == 0 {
            return Vec::new();
        }
        let (head, tail) = names.split_at(shown - 1);
        let mut out: Vec<(String, bool)> = head.iter().map(|n| (n.to_string(), lit(n))).collect();
        out.push(match tail.iter().find(|n| lit(n)) {
            Some(n) => (n.to_string(), true),
            None => (format!("+{} more", tail.len()), false),
        });
        out
    }

    fn draw_sectors(&self, dc: HDC, r: RECT, zoom: &Zoom) {
        unsafe {
            let _ = IntersectClipRect(dc, r.left, r.top, r.right, r.bottom);
        }
        let grid = if zoom.focus.is_some() { zoom.focus_cells() } else { zoom.columns.clone() };
        for col in grid {
            outline(dc, self.column_rect(r, col), 1, MAP_SECTOR_GRID);
        }
        let picked = zoom.lit_column();
        for (c, &col) in zoom.columns.iter().enumerate().filter(|(_, col)| zoom.in_focus(**col)) {
            let cell = self.column_rect(r, col);
            let lines = self.lines(cell, zoom.by_column[c].len());
            for (k, (name, lit)) in Self::labels(zoom, c, lines.shown).iter().enumerate() {
                let top = lines.first + k as i32 * lines.line;
                let at = RECT { left: cell.left + 2, right: cell.right - 2, top, bottom: top + lines.line };
                draw_outlined(dc, self.label.1, at, name, if *lit { MAP_SELECTED } else { MAP_SECTOR_NAME });
            }
        }
        if let Some(c) = picked {
            outline(dc, self.column_rect(r, zoom.columns[c]), PICK_EDGE, MAP_SELECTED);
        }
        if let Some((name, (x0, z0, x1, z1))) = &zoom.outline {
            let (left, top) = self.to_px(r, *x0, *z1);
            let (right, bottom) = self.to_px(r, *x1, *z0);
            let frame = RECT { left: left as i32, top: top as i32, right: right as i32, bottom: bottom as i32 };
            outline(dc, frame, PICK_EDGE, MAP_SELECTED);
            let half = text_width(dc, self.font, name) / 2 + 4;
            let centre = (frame.left + frame.right) / 2;
            let label = RECT { left: centre - half, right: centre + half, top: frame.top - 22, bottom: frame.top - 4 };
            draw_text(dc, self.font, label, name, MAP_SELECTED, true);
        }
        unsafe {
            let _ = SelectClipRgn(dc, None);
        }
    }

    fn draw_legend(&self, dc: HDC, r: RECT) {
        let (_, max) = self.values();
        let decimals = if max < 10.0 { 1 } else { 0 };
        let per = if self.zoom.is_some() { "square" } else { "region" };
        let caption = format!("Expected {} per {per}", KINDS[self.kind].name);
        let bar_w = (r.right - r.left).max(1);
        let labels_top = r.bottom - LEGEND_LINE - 2;
        let bar = RECT { left: r.right - bar_w, right: r.right, top: labels_top - 4 - LEGEND_BAR, bottom: labels_top - 4 };
        let above = RECT { left: r.left, right: r.right, top: bar.top - LEGEND_LINE - 2, bottom: bar.top - 2 };
        let above = RECT { left: bar.left, right: bar.right, ..above };
        draw_aligned(dc, self.font, above, &caption, MAP_LABEL, DT_CENTER | DT_VCENTER);
        for i in 0..bar_w {
            let t = i as f64 / bar_w as f64;
            let c = lerp(MAP_SPACE, gradient(t), (t / MAP_FADE).min(1.0));
            fill(dc, RECT { left: bar.left + i, right: bar.left + i + 1, ..bar }, c);
        }
        let marks = [(0.0, DT_LEFT), (0.5, DT_CENTER), (1.0, DT_RIGHT)];
        for (t, align) in marks {
            let x = bar.left + ((bar_w - 1) as f64 * t) as i32;
            fill(dc, RECT { left: x, right: x + 1, top: bar.bottom, bottom: bar.bottom + 4 }, MAP_LABEL);
            let value = thousands(max * t * t, decimals);
            let label = match align {
                DT_LEFT => RECT { left: x, right: x + 80, top: bar.bottom + 4, bottom: bar.bottom + 18 },
                DT_RIGHT => RECT { left: x - 80, right: x + 1, top: bar.bottom + 4, bottom: bar.bottom + 18 },
                _ => RECT { left: x - 40, right: x + 40, top: bar.bottom + 4, bottom: bar.bottom + 18 },
            };
            draw_aligned(dc, self.font, label, &value, MAP_LABEL, align);
        }
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
        let column = self.column_at(px, py);
        let column_changed = self.zoom.as_ref().is_some_and(|z| z.hover != column);
        if let Some(zoom) = self.zoom.as_mut() {
            zoom.hover = column;
        }
        if hover != self.hover || column_changed {
            self.hover = hover;
            self.invalidate();
        }
    }

    fn mouse_leave(&mut self) {
        self.tracking = false;
        let column = self.zoom.as_mut().and_then(|z| z.hover.take());
        if self.hover.take().is_some() || column.is_some() {
            self.invalidate();
        }
    }

    fn click(&mut self, px: i32, py: i32) -> Option<MapClick> {
        if self.zoom.is_none() {
            let id = self.region_at(px, py)?;
            self.selected = Some(id);
            self.invalidate();
            return Some(MapClick::Region(id as i64));
        }
        let col = self.column_at(px, py)?;
        if let Some(zoom) = self.zoom.as_mut().filter(|z| z.focus.is_none()) {
            if !zoom.loaded {
                return None;
            }
            let rows: Vec<RegionExpected> = zoom.by_column[col].iter().map(|&i| zoom.sectors[i].clone()).collect();
            if rows.is_empty() {
                return Some(MapClick::Unnamed);
            }
            zoom.marked = Some(col);
            self.invalidate();
            return Some(MapClick::Square(rows));
        }
        if !self.zoom.as_ref().is_some_and(|z| z.in_focus(z.columns[col])) {
            return None;
        }
        let cell = self.column_rect(self.map_rect(), self.zoom.as_ref()?.columns[col]);
        let names: Vec<String> = Self::column_names(self.zoom.as_ref()?, col).into_iter().map(String::from).collect();
        let lines = self.lines(cell, names.len());
        let zoom = self.zoom.as_mut()?;
        if !zoom.loaded {
            return None;
        }
        if names.is_empty() {
            return Some(MapClick::Unnamed);
        }
        let k = if lines.shown == 0 { 0 } else { ((py - lines.first).max(0) / lines.line).min(lines.shown as i32 - 1) as usize };
        let next = if lines.shown < names.len() && k + 1 >= lines.shown {
            let tail = &names[lines.shown.saturating_sub(1)..];
            match zoom.picked.as_ref().and_then(|p| tail.iter().position(|n| n == p)) {
                Some(at) => tail[(at + 1) % tail.len()].clone(),
                None => tail[0].clone(),
            }
        } else {
            names[k].clone()
        };
        zoom.picked = Some(next.clone());
        zoom.marked = None;
        zoom.outline = None;
        self.invalidate();
        Some(MapClick::Sector(next))
    }

    fn double_click(&mut self, px: i32, py: i32) -> Option<MapClick> {
        let id = self.region_at(px, py);
        match (&self.zoom, id) {
            (None, Some(id)) => Some(MapClick::Zoom(id as i64)),
            (Some(zoom), Some(id)) if id != zoom.region && self.column_at(px, py).is_none() => Some(MapClick::Zoom(id as i64)),
            (Some(zoom), _) => {
                let column = self.column_at(px, py).map(|c| zoom.columns[c])?;
                if zoom.focus != Some(column) {
                    self.focus_on(column);
                }
                None
            }
            (None, None) => None,
        }
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
        WM_LBUTTONDOWN | WM_LBUTTONDBLCLK => {
            let (x, y) = point(lparam);
            let double = msg == WM_LBUTTONDBLCLK;
            let clicked = main_window::with_map(hwnd, |m| if double { m.double_click(x, y) } else { m.click(x, y) });
            if let Some(Some(click)) = clicked {
                main_window::map_clicked(click);
            }
            LRESULT(0)
        }
        WM_RBUTTONUP => {
            main_window::map_clicked(MapClick::ZoomOut);
            LRESULT(0)
        }
        _ => unsafe { DefWindowProcW(hwnd, msg, wparam, lparam) },
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_region_cell_straddling_a_sector_boundary_touches_both_columns() {
        assert_eq!(column_range(1000), 38..=38);
        assert_eq!(column_range(1011), 38..=39);
        assert_eq!(column_range(1012), 39..=39);
        assert_eq!(column_range(1380), 53..=53);
    }

    #[test]
    fn region_columns_cover_every_cell_of_the_region() {
        let mut regions = vec![0u8; MAP_GRID * MAP_GRID];
        regions[1380 * MAP_GRID + 1000..1380 * MAP_GRID + 1005].fill(7);
        regions[1381 * MAP_GRID + 1010..1381 * MAP_GRID + 1013].fill(7);
        regions[1380 * MAP_GRID + 1040..1380 * MAP_GRID + 1045].fill(8);
        assert_eq!(region_columns(&regions, 7), vec![(38, 53), (39, 53)]);
        assert_eq!(region_columns(&regions, 8), vec![(40, 53)]);
        assert!(region_columns(&regions, 9).is_empty());
    }
}
