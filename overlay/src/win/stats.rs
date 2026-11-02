use windows::Win32::Foundation::{HINSTANCE, HWND, LPARAM, LRESULT, POINT, RECT, WPARAM};
use windows::Win32::Graphics::Gdi::{
    BeginPaint, BitBlt, CreateCompatibleBitmap, CreateCompatibleDC, CreatePen, CreateSolidBrush, DT_CENTER, DT_RIGHT, DT_VCENTER,
    DeleteDC, DeleteObject, Ellipse, EndPaint, HDC, HFONT, HGDIOBJ, InvalidateRect, PAINTSTRUCT, PS_SOLID, Polyline, SRCCOPY,
    SelectObject, SetBkMode, TRANSPARENT,
};
use windows::Win32::System::LibraryLoader::GetModuleHandleW;
use windows::Win32::UI::Controls::WM_MOUSELEAVE;
use windows::Win32::UI::Input::KeyboardAndMouse::{TME_LEAVE, TRACKMOUSEEVENT, TrackMouseEvent};
use windows::Win32::UI::WindowsAndMessaging::{
    CreateWindowExW, DefWindowProcW, GetClientRect, IDC_ARROW, LoadCursorW, RegisterClassExW, WINDOW_EX_STYLE, WM_ERASEBKGND,
    WM_MOUSEMOVE, WM_PAINT, WNDCLASSEXW, WS_CHILD, WS_CLIPSIBLINGS,
};
use windows::core::{PCWSTR, w};

use crate::database::{DayCounts, Stats};
use crate::kinds::KINDS;
use crate::table::thousands_i;
use crate::theme::{HEADER_LINE, HEADER_TEXT, MAP_LABEL, MAP_SPACE, Rgb, STATS_GRID, STATS_KIND, STATS_TIP_BG, TABLE_TEXT};

use super::expected_table::{colorref, fill};
use super::main_window;
use super::map::{draw_aligned, draw_text, text_width};

const PAD: i32 = 16;
const TITLE_H: i32 = 22;
const LEGEND_H: i32 = 20;
const AXIS_W: i32 = 44;
const DAYS_H: i32 = 22;
const SWATCH: i32 = 10;
const LINE_W: i32 = 2;
const MARKER: i32 = 4;
const LABEL_GAP: i32 = 12;
const TIP_ROW: i32 = 16;
const TIP_PAD: i32 = 8;
const DECADES: [i64; 5] = [0, 1, 10, 100, 1000];

const TITLES: [&str; 2] = ["Objects visited per day", "Objects confirmed per day"];
const NOTES: [&str; 2] = ["first arrival, UTC, log scale", "the day the arrival class was revealed, log scale"];
const EMPTY: [&str; 2] = ["No dated visit to a confirmed object yet", "No dated find yet"];

pub struct StatsView {
    pub hwnd: HWND,
    stats: Option<Stats>,
    font: HFONT,
    small: HFONT,
    hover: Option<(usize, usize, i32, i32)>,
    tracking: bool,
}

fn level(n: i64) -> f64 {
    ((n.max(0) + 1) as f64).log10()
}

fn short_day(day: &str) -> &str {
    day.get(5..).unwrap_or(day)
}

struct Plot {
    area: RECT,
    top: f64,
}

impl Plot {
    fn x(&self, i: usize, days: usize) -> i32 {
        let w = (self.area.right - self.area.left) as f64;
        if days <= 1 {
            return self.area.left + (w / 2.0) as i32;
        }
        self.area.left + (w * i as f64 / (days - 1) as f64).round() as i32
    }

    fn y(&self, n: i64) -> i32 {
        let h = (self.area.bottom - self.area.top) as f64;
        self.area.bottom - (h * level(n) / self.top).round() as i32
    }
}

fn pen_line(dc: HDC, pts: &[POINT], c: Rgb, width: i32) {
    unsafe {
        let pen = CreatePen(PS_SOLID, width, colorref(c));
        let old = SelectObject(dc, HGDIOBJ(pen.0));
        let _ = Polyline(dc, pts);
        SelectObject(dc, old);
        let _ = DeleteObject(HGDIOBJ(pen.0));
    }
}

fn marker(dc: HDC, p: POINT, c: Rgb) {
    unsafe {
        let pen = CreatePen(PS_SOLID, LINE_W, colorref(MAP_SPACE));
        let brush = CreateSolidBrush(colorref(c));
        let old_pen = SelectObject(dc, HGDIOBJ(pen.0));
        let old_brush = SelectObject(dc, HGDIOBJ(brush.0));
        let _ = Ellipse(dc, p.x - MARKER, p.y - MARKER, p.x + MARKER + 1, p.y + MARKER + 1);
        SelectObject(dc, old_pen);
        SelectObject(dc, old_brush);
        let _ = DeleteObject(HGDIOBJ(pen.0));
        let _ = DeleteObject(HGDIOBJ(brush.0));
    }
}

impl StatsView {
    pub fn create(parent: HWND, instance: HINSTANCE) -> Result<StatsView, String> {
        unsafe {
            let class = WNDCLASSEXW {
                cbSize: std::mem::size_of::<WNDCLASSEXW>() as u32,
                lpfnWndProc: Some(wndproc),
                hInstance: GetModuleHandleW(None).map_err(|e| e.to_string())?.into(),
                hCursor: LoadCursorW(None, IDC_ARROW).unwrap_or_default(),
                lpszClassName: w!("EdOverlayStats"),
                ..Default::default()
            };
            RegisterClassExW(&class);
            let hwnd = CreateWindowExW(
                WINDOW_EX_STYLE::default(),
                w!("EdOverlayStats"),
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
            Ok(StatsView { hwnd, stats: None, font: HFONT::default(), small: HFONT::default(), hover: None, tracking: false })
        }
    }

    pub fn set_fonts(&mut self, font: HFONT, small: HFONT) {
        self.font = font;
        self.small = small;
        self.invalidate();
    }

    pub fn show(&mut self, stats: Stats) {
        self.stats = Some(stats);
        self.hover = None;
        self.invalidate();
    }

    fn invalidate(&self) {
        unsafe {
            let _ = InvalidateRect(Some(self.hwnd), None, false);
        }
    }

    fn charts(&self) -> [RECT; 2] {
        let mut c = RECT::default();
        unsafe {
            let _ = GetClientRect(self.hwnd, &mut c);
        }
        let half = (c.bottom - c.top) / 2;
        [RECT { bottom: c.top + half, ..c }, RECT { top: c.top + half, ..c }]
    }

    fn days(&self, chart: usize) -> &[DayCounts] {
        match &self.stats {
            Some(s) if chart == 0 => &s.visited,
            Some(s) => &s.confirmed,
            None => &[],
        }
    }

    fn plot(&self, chart: usize, r: RECT) -> Plot {
        let area = RECT {
            left: r.left + PAD + AXIS_W,
            top: r.top + PAD + TITLE_H + LEGEND_H + PAD / 2,
            right: r.right - PAD * 2,
            bottom: r.bottom - PAD - DAYS_H,
        };
        let max = self.days(chart).iter().flat_map(|d| d.n).max().unwrap_or(0);
        let decade = DECADES.iter().copied().find(|&d| d >= max).unwrap_or_else(|| 10i64.pow((max as f64).log10().ceil() as u32));
        Plot { area, top: level(decade).max(level(1)) }
    }

    fn paint(&self) {
        let mut client = RECT::default();
        unsafe {
            let _ = GetClientRect(self.hwnd, &mut client);
            let (w, h) = (client.right.max(1), client.bottom.max(1));
            let mut ps = PAINTSTRUCT::default();
            let hdc = BeginPaint(self.hwnd, &mut ps);
            let mem = CreateCompatibleDC(Some(hdc));
            let bmp = CreateCompatibleBitmap(hdc, w, h);
            let old = SelectObject(mem, HGDIOBJ(bmp.0));
            fill(mem, client, MAP_SPACE);
            SetBkMode(mem, TRANSPARENT);
            for (chart, r) in self.charts().into_iter().enumerate() {
                self.draw_chart(mem, chart, r);
            }
            if let Some((chart, day, mx, my)) = self.hover {
                self.draw_tip(mem, chart, day, mx, my, client);
            }
            let _ = BitBlt(hdc, 0, 0, w, h, Some(mem), 0, 0, SRCCOPY);
            SelectObject(mem, old);
            let _ = DeleteObject(HGDIOBJ(bmp.0));
            let _ = DeleteDC(mem);
            let _ = EndPaint(self.hwnd, &ps);
        }
    }

    fn draw_chart(&self, dc: HDC, chart: usize, r: RECT) {
        let days = self.days(chart);
        let title = RECT { left: r.left + PAD, right: r.right - PAD, top: r.top + PAD, bottom: r.top + PAD + TITLE_H };
        draw_text(dc, self.font, title, TITLES[chart], HEADER_TEXT, false);
        let note_left = title.left + text_width(dc, self.font, TITLES[chart]) + LABEL_GAP;
        draw_text(dc, self.small, RECT { left: note_left, ..title }, NOTES[chart], MAP_LABEL, false);
        if self.stats.is_none() {
            draw_text(dc, self.font, r, "loading\u{2026}", TABLE_TEXT, true);
            return;
        }
        if days.is_empty() {
            draw_text(dc, self.font, r, EMPTY[chart], TABLE_TEXT, true);
            return;
        }
        self.draw_legend(dc, days, RECT { top: title.bottom, bottom: title.bottom + LEGEND_H, ..title });
        let plot = self.plot(chart, r);
        let a = plot.area;
        for &d in DECADES.iter().filter(|&&d| level(d) <= plot.top + 1e-9) {
            let y = plot.y(d);
            fill(dc, RECT { left: a.left, right: a.right, top: y, bottom: y + 1 }, if d == 0 { HEADER_LINE } else { STATS_GRID });
            let label = RECT { left: r.left + PAD, right: a.left - 6, top: y - 8, bottom: y + 8 };
            draw_aligned(dc, self.small, label, &thousands_i(d), MAP_LABEL, DT_RIGHT | DT_VCENTER);
        }
        let widest = days.iter().map(|d| text_width(dc, self.small, short_day(&d.day))).max().unwrap_or(0) + LABEL_GAP;
        let span = (plot.x(days.len().saturating_sub(1), days.len()) - plot.x(0, days.len())).max(1);
        let stride = if days.len() <= 1 { 1 } else { ((widest * (days.len() - 1) as i32) / span + 1).max(1) as usize };
        for (i, d) in days.iter().enumerate() {
            if i % stride != 0 {
                continue;
            }
            let x = plot.x(i, days.len());
            fill(dc, RECT { left: x, right: x + 1, top: a.bottom, bottom: a.bottom + 4 }, HEADER_LINE);
            let label = RECT { left: x - widest / 2, right: x + widest / 2, top: a.bottom + 4, bottom: a.bottom + DAYS_H };
            draw_aligned(dc, self.small, label, short_day(&d.day), MAP_LABEL, DT_CENTER | DT_VCENTER);
        }
        if let Some((_, day, _, _)) = self.hover.filter(|h| h.0 == chart) {
            let x = plot.x(day, days.len());
            fill(dc, RECT { left: x, right: x + 1, top: a.top, bottom: a.bottom }, HEADER_LINE);
        }
        for (k, &colour) in STATS_KIND.iter().enumerate() {
            if days.iter().all(|d| d.n[k] == 0) {
                continue;
            }
            let pts: Vec<POINT> = days.iter().enumerate().map(|(i, d)| POINT { x: plot.x(i, days.len()), y: plot.y(d.n[k]) }).collect();
            pen_line(dc, &pts, colour, LINE_W);
            for (p, d) in pts.iter().zip(days) {
                if d.n[k] > 0 {
                    marker(dc, *p, colour);
                }
            }
        }
    }

    fn draw_legend(&self, dc: HDC, days: &[DayCounts], r: RECT) {
        let mut x = r.left;
        for (k, kind) in KINDS.iter().enumerate() {
            let total: i64 = days.iter().map(|d| d.n[k]).sum();
            let label = format!("{} {}", kind.title(), thousands_i(total));
            let mid = (r.top + r.bottom) / 2;
            fill(dc, RECT { left: x, right: x + SWATCH, top: mid - SWATCH / 2, bottom: mid + SWATCH / 2 }, STATS_KIND[k]);
            let w = text_width(dc, self.small, &label);
            draw_text(dc, self.small, RECT { left: x + SWATCH + 5, right: x + SWATCH + 5 + w + 1, ..r }, &label, MAP_LABEL, false);
            x += SWATCH + 5 + w + LABEL_GAP * 2;
        }
    }

    fn draw_tip(&self, dc: HDC, chart: usize, day: usize, mx: i32, my: i32, client: RECT) {
        let Some(d) = self.days(chart).get(day) else { return };
        let rows: Vec<(Option<usize>, String)> = std::iter::once((None, d.day.clone()))
            .chain(KINDS.iter().enumerate().filter(|(k, _)| d.n[*k] > 0).map(|(k, kind)| (Some(k), format!("{}  {}", kind.title(), thousands_i(d.n[k])))))
            .chain(std::iter::once((None, format!("Total  {}", thousands_i(d.n.iter().sum())))))
            .collect();
        let w = rows.iter().map(|(_, s)| text_width(dc, self.small, s)).max().unwrap_or(0) + SWATCH + 5 + TIP_PAD * 2;
        let h = rows.len() as i32 * TIP_ROW + TIP_PAD * 2;
        let left = if mx + 16 + w > client.right { mx - 16 - w } else { mx + 16 };
        let top = (my - h / 2).clamp(client.top, (client.bottom - h).max(client.top));
        let tip = RECT { left, top, right: left + w, bottom: top + h };
        fill(dc, tip, STATS_TIP_BG);
        for edge in [
            RECT { bottom: tip.top + 1, ..tip },
            RECT { top: tip.bottom - 1, ..tip },
            RECT { right: tip.left + 1, ..tip },
            RECT { left: tip.right - 1, ..tip },
        ] {
            fill(dc, edge, HEADER_LINE);
        }
        for (i, (k, text)) in rows.iter().enumerate() {
            let y = tip.top + TIP_PAD + i as i32 * TIP_ROW;
            let row = RECT { left: tip.left + TIP_PAD + SWATCH + 5, right: tip.right - TIP_PAD, top: y, bottom: y + TIP_ROW };
            if let Some(k) = k {
                let mid = y + TIP_ROW / 2;
                fill(dc, RECT { left: tip.left + TIP_PAD, right: tip.left + TIP_PAD + SWATCH, top: mid - SWATCH / 2, bottom: mid + SWATCH / 2 }, STATS_KIND[*k]);
            }
            let ink = if k.is_none() { HEADER_TEXT } else { MAP_LABEL };
            draw_text(dc, self.small, row, text, ink, false);
        }
    }

    fn mouse_move(&mut self, px: i32, py: i32) {
        if !self.tracking {
            let mut track = TRACKMOUSEEVENT { cbSize: std::mem::size_of::<TRACKMOUSEEVENT>() as u32, dwFlags: TME_LEAVE, hwndTrack: self.hwnd, dwHoverTime: 0 };
            unsafe {
                let _ = TrackMouseEvent(&mut track);
            }
            self.tracking = true;
        }
        let hover = self.charts().into_iter().enumerate().find_map(|(chart, r)| {
            let days = self.days(chart);
            let plot = self.plot(chart, r);
            let a = plot.area;
            if days.is_empty() || py < a.top || py > a.bottom || px < a.left - MARKER * 2 || px > a.right + MARKER * 2 {
                return None;
            }
            let day = (0..days.len()).min_by_key(|&i| (plot.x(i, days.len()) - px).abs())?;
            Some((chart, day, px, py))
        });
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
}

fn point(lparam: LPARAM) -> (i32, i32) {
    ((lparam.0 & 0xffff) as i16 as i32, ((lparam.0 >> 16) & 0xffff) as i16 as i32)
}

unsafe extern "system" fn wndproc(hwnd: HWND, msg: u32, wparam: WPARAM, lparam: LPARAM) -> LRESULT {
    match msg {
        WM_PAINT => {
            if main_window::with_stats(|s| s.paint()).is_none() {
                return unsafe { DefWindowProcW(hwnd, msg, wparam, lparam) };
            }
            LRESULT(0)
        }
        WM_ERASEBKGND => LRESULT(1),
        WM_MOUSEMOVE => {
            let (x, y) = point(lparam);
            main_window::with_stats(|s| s.mouse_move(x, y));
            LRESULT(0)
        }
        WM_MOUSELEAVE => {
            main_window::with_stats(|s| s.mouse_leave());
            LRESULT(0)
        }
        _ => unsafe { DefWindowProcW(hwnd, msg, wparam, lparam) },
    }
}
