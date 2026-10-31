use windows::Win32::Foundation::{HINSTANCE, HWND, LPARAM, LRESULT, RECT, SIZE, WPARAM};
use windows::Win32::Graphics::Gdi::{
    BeginPaint, DRAW_TEXT_FORMAT, DT_CENTER, DT_LEFT, DT_NOPREFIX, DT_SINGLELINE, DT_VCENTER, DT_END_ELLIPSIS, DrawTextW, EndPaint,
    GetTextExtentPoint32W, HDC, HFONT, HGDIOBJ, InvalidateRect, PAINTSTRUCT, SelectObject, SetBkMode, SetTextColor,
    TRANSPARENT,
};
use windows::Win32::System::LibraryLoader::GetModuleHandleW;
use windows::Win32::UI::HiDpi::GetDpiForWindow;
use windows::Win32::UI::WindowsAndMessaging::{
    CreateWindowExW, DefWindowProcW, GetClientRect, IDC_ARROW, KillTimer, LoadCursorW, RegisterClassExW, SetTimer,
    WINDOW_EX_STYLE, WM_ERASEBKGND, WM_LBUTTONDOWN, WM_PAINT, WM_TIMER, WNDCLASSEXW, WS_CHILD, WS_CLIPSIBLINGS,
};
use windows::core::{PCWSTR, w};

use crate::market::{BULK_SUPPLY, FRESH_DAYS, Quotes, RADIUS_LY, Tritium};
use crate::table::{light_years, thousands_i};
use crate::theme::{FLASH_TEXT, HEADER_BG, HEADER_LINE, HEADER_TEXT, MAP_LABEL, Rgb, TABLE_FLASH, TABLE_ROW, TABLE_TEXT};
use crate::win::clipboard;

use super::expected_table::{colorref, fill};
use super::main_window;

const PAD: i32 = 16;
const LABEL_W: i32 = 96;
const ROW_GAP: i32 = 6;
const SECTION_GAP: i32 = 18;
const BUTTON_W: i32 = 64;
const BUTTON_GAP: i32 = 12;
const FLASH_TIMER: usize = 1;
const FLASH_MS: u32 = 350;
const COPY: &str = "Copy";

#[derive(Clone, Debug)]
pub struct Field {
    pub label: String,
    pub value: String,
    pub copy: bool,
}

impl Field {
    pub fn text(label: &str, value: impl Into<String>) -> Field {
        Field { label: label.to_string(), value: value.into(), copy: false }
    }

    pub fn system(label: &str, value: impl Into<String>) -> Field {
        let value = value.into();
        Field { label: label.to_string(), copy: !value.is_empty(), value }
    }
}

#[derive(Clone, Debug)]
pub struct Section {
    pub heading: String,
    pub fields: Vec<Field>,
}

pub struct CarrierCard {
    pub hwnd: HWND,
    carrier: Vec<Section>,
    tritium: Quotes,
    buttons: Vec<(RECT, String)>,
    flash: Option<usize>,
    font: HFONT,
    small: HFONT,
    big: HFONT,
}

fn tritium_section(heading: String, t: &Tritium, none: String) -> Section {
    let fields = match t {
        Tritium::Waiting => vec![Field::text("Status", "waiting for the ship's position")],
        Tritium::Searching => vec![Field::text("Status", "asking Spansh\u{2026}")],
        Tritium::NoneNear => vec![Field::text("Status", format!("{none} (prices from the last {FRESH_DAYS} days)"))],
        Tritium::Failed(e) => vec![Field::text("Status", format!("Spansh did not answer: {e}"))],
        Tritium::Found(q) => {
            let age = match q.age_days {
                Some(0) => "updated today".to_string(),
                Some(1) => "updated 1 day ago".to_string(),
                Some(d) => format!("updated {d} days ago"),
                None => "update time unknown".to_string(),
            };
            vec![
                Field::system("System", q.system.clone()),
                Field::text("Station", format!("{}  \u{00B7}  {}", q.station, q.station_type)),
                Field::text("Distance", format!("{} ly", light_years(q.dist_ly))),
                Field::text("Price", format!("{} Cr  \u{00B7}  {} t in stock  \u{00B7}  {age}", thousands_i(q.price), thousands_i(q.supply))),
            ]
        }
    };
    Section { heading, fields }
}

fn extent(dc: HDC, text: &str) -> SIZE {
    let wide: Vec<u16> = text.encode_utf16().collect();
    let mut size = SIZE::default();
    unsafe {
        let _ = GetTextExtentPoint32W(dc, &wide, &mut size);
    }
    size
}

fn text(dc: HDC, font: HFONT, s: &str, colour: Rgb, mut area: RECT, format: DRAW_TEXT_FORMAT) {
    let mut wide: Vec<u16> = s.encode_utf16().collect();
    unsafe {
        SelectObject(dc, HGDIOBJ(font.0));
        SetTextColor(dc, colorref(colour));
        DrawTextW(dc, &mut wide, &mut area, format | DT_SINGLELINE | DT_NOPREFIX);
    }
}

impl CarrierCard {
    pub fn create(parent: HWND, instance: HINSTANCE) -> Result<CarrierCard, String> {
        unsafe {
            let class = WNDCLASSEXW {
                cbSize: std::mem::size_of::<WNDCLASSEXW>() as u32,
                lpfnWndProc: Some(wndproc),
                hInstance: GetModuleHandleW(None).map_err(|e| e.to_string())?.into(),
                hCursor: LoadCursorW(None, IDC_ARROW).unwrap_or_default(),
                lpszClassName: w!("EdOverlayCarrier"),
                ..Default::default()
            };
            RegisterClassExW(&class);
            let hwnd = CreateWindowExW(
                WINDOW_EX_STYLE::default(),
                w!("EdOverlayCarrier"),
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
            Ok(CarrierCard {
                hwnd,
                carrier: Vec::new(),
                tritium: Quotes::all(Tritium::Waiting),
                buttons: Vec::new(),
                flash: None,
                font: HFONT::default(),
                small: HFONT::default(),
                big: HFONT::default(),
            })
        }
    }

    pub fn set_fonts(&mut self, font: HFONT, small: HFONT, big: HFONT) {
        (self.font, self.small, self.big) = (font, small, big);
        self.invalidate();
    }

    pub fn show_carrier(&mut self, sections: Vec<Section>) {
        self.carrier = sections;
        self.invalidate();
    }

    pub fn show_tritium(&mut self, quotes: Quotes) {
        self.tritium = quotes;
        self.invalidate();
    }

    fn invalidate(&self) {
        unsafe {
            let _ = InvalidateRect(Some(self.hwnd), None, false);
        }
    }

    fn sections(&self) -> Vec<Section> {
        let mut all = self.carrier.clone();
        all.push(tritium_section(
            "Tritium, cheapest".into(),
            &self.tritium.cheapest,
            format!("no station sells it within {} ly", light_years(RADIUS_LY.into())),
        ));
        all.push(tritium_section(
            format!("Tritium, {} t or more", thousands_i(BULK_SUPPLY)),
            &self.tritium.bulk,
            format!("no station holds {} t", thousands_i(BULK_SUPPLY)),
        ));
        all
    }

    fn paint(&mut self) {
        let dpi = unsafe { GetDpiForWindow(self.hwnd) }.max(96) as i32;
        let px = |v: i32| v * dpi / 96;
        let mut client = RECT::default();
        let mut ps = PAINTSTRUCT::default();
        let sections = self.sections();
        let mut buttons = Vec::new();
        unsafe {
            let _ = GetClientRect(self.hwnd, &mut client);
            let dc = BeginPaint(self.hwnd, &mut ps);
            fill(dc, client, TABLE_ROW);
            SetBkMode(dc, TRANSPARENT);
            let old = SelectObject(dc, HGDIOBJ(self.big.0));
            let line_big = extent(dc, "Hg").cy + px(ROW_GAP);
            SelectObject(dc, HGDIOBJ(self.small.0));
            let line_small = extent(dc, "Hg").cy;
            let (left, right) = (client.left + px(PAD), client.right - px(PAD));
            let value_left = left + px(LABEL_W);
            let mut y = client.top + px(PAD);
            for (i, section) in sections.iter().enumerate() {
                if i > 0 {
                    y += px(SECTION_GAP) / 2;
                    fill(dc, RECT { left, right, top: y, bottom: y + 1 }, HEADER_LINE);
                    y += px(SECTION_GAP) / 2;
                }
                let heading = section.heading.to_uppercase();
                text(dc, self.small, &heading, HEADER_TEXT, RECT { left, right, top: y, bottom: y + line_small }, DT_LEFT);
                y += line_small + px(ROW_GAP);
                for field in &section.fields {
                    let row = RECT { left, right, top: y, bottom: y + line_big - px(ROW_GAP) };
                    text(dc, self.font, &field.label, TABLE_TEXT, RECT { right: value_left, ..row }, DT_LEFT | DT_VCENTER);
                    let room = right - value_left - if field.copy { px(BUTTON_W + BUTTON_GAP) } else { 0 };
                    let colour = if field.copy { MAP_LABEL } else { TABLE_TEXT };
                    text(dc, self.big, &field.value, colour, RECT { left: value_left, right: value_left + room, ..row }, DT_LEFT | DT_VCENTER | DT_END_ELLIPSIS);
                    if field.copy {
                        let bx = right - px(BUTTON_W);
                        let button = RECT { left: bx, right: bx + px(BUTTON_W), top: row.top, bottom: row.bottom };
                        let pressed = self.flash == Some(buttons.len());
                        draw_button(dc, self.font, button, pressed);
                        buttons.push((button, field.value.clone()));
                    }
                    y += line_big;
                }
            }
            SelectObject(dc, old);
            let _ = EndPaint(self.hwnd, &ps);
        }
        self.buttons = buttons;
    }

    fn click(&mut self, x: i32, y: i32) {
        let Some(i) = self.buttons.iter().position(|(r, _)| x >= r.left && x < r.right && y >= r.top && y < r.bottom) else {
            return;
        };
        let system = self.buttons[i].1.clone();
        if clipboard::copy(&system) {
            crate::say!("copied {system} to the clipboard");
        }
        self.flash = Some(i);
        self.invalidate();
        unsafe {
            SetTimer(Some(self.hwnd), FLASH_TIMER, FLASH_MS, None);
        }
    }

    fn end_flash(&mut self) {
        unsafe {
            let _ = KillTimer(Some(self.hwnd), FLASH_TIMER);
        }
        self.flash = None;
        self.invalidate();
    }
}

fn draw_button(dc: HDC, font: HFONT, r: RECT, pressed: bool) {
    let (back, label) = if pressed { (TABLE_FLASH, FLASH_TEXT) } else { (HEADER_BG, HEADER_TEXT) };
    fill(dc, r, back);
    for edge in [
        RECT { bottom: r.top + 1, ..r },
        RECT { top: r.bottom - 1, ..r },
        RECT { right: r.left + 1, ..r },
        RECT { left: r.right - 1, ..r },
    ] {
        fill(dc, edge, HEADER_LINE);
    }
    text(dc, font, COPY, label, r, DT_CENTER | DT_VCENTER);
}

fn point(lparam: LPARAM) -> (i32, i32) {
    ((lparam.0 & 0xffff) as i16 as i32, ((lparam.0 >> 16) & 0xffff) as i16 as i32)
}

unsafe extern "system" fn wndproc(hwnd: HWND, msg: u32, wparam: WPARAM, lparam: LPARAM) -> LRESULT {
    match msg {
        WM_PAINT => {
            if main_window::with_carrier(|c| c.paint()).is_none() {
                return unsafe { DefWindowProcW(hwnd, msg, wparam, lparam) };
            }
            LRESULT(0)
        }
        WM_ERASEBKGND => LRESULT(1),
        WM_LBUTTONDOWN => {
            let (x, y) = point(lparam);
            main_window::with_carrier(|c| c.click(x, y));
            LRESULT(0)
        }
        WM_TIMER if wparam.0 == FLASH_TIMER => {
            main_window::with_carrier(|c| c.end_flash());
            LRESULT(0)
        }
        _ => unsafe { DefWindowProcW(hwnd, msg, wparam, lparam) },
    }
}
