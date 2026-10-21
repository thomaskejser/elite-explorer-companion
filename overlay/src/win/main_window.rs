use std::cell::{Cell, RefCell};
use std::fs::File;
use std::io::{Read, Seek, SeekFrom};
use std::path::{Path, PathBuf};

use windows::Win32::Foundation::{HWND, LPARAM, LRESULT, RECT, WPARAM};
use windows::Win32::Graphics::Gdi::{
    CLIP_DEFAULT_PRECIS, CLEARTYPE_QUALITY, COLOR_BTNFACE, CreateFontW, DEFAULT_CHARSET, DeleteObject, FF_DONTCARE,
    FF_MODERN, FIXED_PITCH, FW_NORMAL, HBRUSH, HFONT, HGDIOBJ, OUT_DEFAULT_PRECIS, VARIABLE_PITCH,
};
use windows::Win32::System::LibraryLoader::GetModuleHandleW;
use windows::Win32::UI::Controls::{
    EM_GETFIRSTVISIBLELINE, EM_GETSEL, EM_LINEFROMCHAR, EM_LINEINDEX, EM_LINESCROLL, EM_REPLACESEL, EM_SETLIMITTEXT,
    EM_SETSEL, ICC_LISTVIEW_CLASSES, ICC_TAB_CLASSES, INITCOMMONCONTROLSEX, InitCommonControlsEx, LVN_COLUMNCLICK,
    NMHDR, NMLISTVIEW, TCIF_TEXT, TCITEMW,
    TCM_ADJUSTRECT, TCM_GETCURSEL, TCM_INSERTITEMW, TCN_SELCHANGE, WC_TABCONTROLW,
};
use windows::Win32::UI::HiDpi::GetDpiForWindow;
use windows::Win32::UI::WindowsAndMessaging::{
    CW_USEDEFAULT, CreateWindowExW, DefWindowProcW, ES_AUTOVSCROLL, ES_MULTILINE, ES_NOHIDESEL, ES_READONLY,
    GetClientRect, GetScrollInfo, IDC_ARROW, KillTimer, LoadCursorW, MoveWindow, PostQuitMessage,
    RegisterClassExW, SB_VERT, SCROLLINFO, SIF_ALL, SW_HIDE, SW_SHOW, SW_SHOWNOACTIVATE, SWP_NOACTIVATE,
    SWP_NOMOVE, SWP_NOZORDER, SendMessageW, SetTimer, SetWindowPos, ShowWindow, WINDOW_EX_STYLE, WINDOW_STYLE, WM_DESTROY,
    WM_DPICHANGED, WM_NOTIFY, WM_SETFONT, WM_SIZE, WM_TIMER, WNDCLASSEXW, WS_CHILD, WS_CLIPCHILDREN,
    WS_CLIPSIBLINGS, WS_EX_CLIENTEDGE, WS_OVERLAPPEDWINDOW, WS_TABSTOP, WS_VISIBLE, WS_VSCROLL,
};
use windows::core::{PCWSTR, PWSTR, w};

use crate::database::RegionExpected;
use crate::win::regions::RegionsView;

pub const TITLE: &str = "ed-overlay";

const LOG_TIMER: usize = 1;
const LOG_POLL_MS: u32 = 250;
const LOG_BACKLOG_BYTES: u64 = 512 << 10;
const LOG_MAX_CHARS: usize = 2 << 20;
const LOG_KEEP_CHARS: usize = 1 << 20;

const REGIONS_TAB: isize = 1;

thread_local! {
    static MAIN: RefCell<Option<MainWindow>> = const { RefCell::new(None) };
    static REGIONS_WANTED: Cell<bool> = const { Cell::new(true) };
}

pub fn take_regions_wanted() -> bool {
    REGIONS_WANTED.replace(false)
}

pub fn show_regions(rows: Vec<RegionExpected>) {
    with_main(|m| m.regions.show(rows));
}

pub(super) fn wide(text: &str) -> Vec<u16> {
    text.encode_utf16().chain(std::iter::once(0)).collect()
}

pub(super) fn send(hwnd: HWND, msg: u32, wparam: usize, lparam: isize) -> isize {
    unsafe { SendMessageW(hwnd, msg, Some(WPARAM(wparam)), Some(LPARAM(lparam))).0 }
}

fn font(name: &str, pt: i32, dpi: i32, family: u32) -> HFONT {
    let face = wide(name);
    unsafe {
        CreateFontW(
            -(pt * dpi / 72),
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
            family,
            PCWSTR(face.as_ptr()),
        )
    }
}

struct Fonts {
    ui: HFONT,
    mono: HFONT,
}

impl Fonts {
    fn new(dpi: i32) -> Fonts {
        Fonts {
            ui: font("Segoe UI", 9, dpi, (VARIABLE_PITCH.0 | FF_DONTCARE.0) as u32),
            mono: font("Consolas", 10, dpi, (FIXED_PITCH.0 | FF_MODERN.0) as u32),
        }
    }
}

impl Drop for Fonts {
    fn drop(&mut self) {
        unsafe {
            let _ = DeleteObject(HGDIOBJ(self.ui.0));
            let _ = DeleteObject(HGDIOBJ(self.mono.0));
        }
    }
}

struct LogView {
    edit: HWND,
    path: PathBuf,
    offset: u64,
    pending: Vec<u8>,
    chars: usize,
}

impl LogView {
    fn read_new(&mut self) -> Option<String> {
        let mut file = File::open(&self.path).ok()?;
        let len = file.metadata().ok()?.len();
        if len < self.offset {
            self.offset = 0;
            self.pending.clear();
        }
        if len == self.offset {
            return None;
        }
        let first = self.offset == 0 && self.chars == 0;
        let start = if first { len.saturating_sub(LOG_BACKLOG_BYTES) } else { self.offset };
        file.seek(SeekFrom::Start(start)).ok()?;
        let mut bytes = Vec::with_capacity((len - start) as usize);
        file.take(len - start).read_to_end(&mut bytes).ok()?;
        self.offset = start + bytes.len() as u64;
        if first && start > 0 {
            let cut = bytes.iter().position(|&b| b == b'\n').map_or(bytes.len(), |i| i + 1);
            bytes.drain(..cut);
        }
        self.pending.extend_from_slice(&bytes);
        let end = self.pending.iter().rposition(|&b| b == b'\n')? + 1;
        let complete: Vec<u8> = self.pending.drain(..end).collect();
        let text = String::from_utf8_lossy(&complete).replace("\r\n", "\n").replace('\n', "\r\n");
        Some(text)
    }

    fn poll(&mut self) {
        let Some(text) = self.read_new() else { return };
        let mut info = SCROLLINFO { cbSize: std::mem::size_of::<SCROLLINFO>() as u32, fMask: SIF_ALL, ..Default::default() };
        let at_bottom = unsafe { GetScrollInfo(self.edit, SB_VERT, &mut info) }.is_err()
            || info.nPos + info.nPage as i32 >= info.nMax;
        let first_line = send(self.edit, EM_GETFIRSTVISIBLELINE, 0, 0);
        let (mut sel_start, mut sel_end) = (0u32, 0u32);
        send(self.edit, EM_GETSEL, &mut sel_start as *mut u32 as usize, &mut sel_end as *mut u32 as isize);

        let removed = self.trim(text.encode_utf16().count());
        let body = wide(&text);
        send(self.edit, EM_SETSEL, self.chars, self.chars as isize);
        send(self.edit, EM_REPLACESEL, 0, body.as_ptr() as isize);
        self.chars += body.len() - 1;

        if at_bottom {
            return;
        }
        let keep = |p: u32| (p as usize).saturating_sub(removed);
        send(self.edit, EM_SETSEL, keep(sel_start), keep(sel_end) as isize);
        let removed_lines = if removed == 0 { 0 } else { send(self.edit, EM_LINEFROMCHAR, 0, 0) };
        let target = (first_line - removed_lines).max(0);
        let now = send(self.edit, EM_GETFIRSTVISIBLELINE, 0, 0);
        send(self.edit, EM_LINESCROLL, 0, target - now);
    }

    fn trim(&mut self, incoming: usize) -> usize {
        if self.chars + incoming <= LOG_MAX_CHARS {
            return 0;
        }
        let cut_at = (self.chars + incoming).saturating_sub(LOG_KEEP_CHARS).min(self.chars);
        let line = send(self.edit, EM_LINEFROMCHAR, cut_at, 0);
        let next = send(self.edit, EM_LINEINDEX, (line + 1) as usize, 0);
        let cut = if next < 0 { self.chars } else { next as usize };
        let empty = wide("");
        send(self.edit, EM_SETSEL, 0, cut as isize);
        send(self.edit, EM_REPLACESEL, 0, empty.as_ptr() as isize);
        self.chars -= cut;
        cut
    }
}

pub struct MainWindow {
    hwnd: HWND,
    tabs: HWND,
    pages: Vec<HWND>,
    log: LogView,
    regions: RegionsView,
    fonts: Fonts,
}

impl MainWindow {
    pub fn open(log_path: &Path) -> Result<(), String> {
        let window = MainWindow::create(log_path)?;
        MAIN.with(|cell| *cell.borrow_mut() = Some(window));
        with_main(|m| {
            m.log.poll();
            unsafe { SetTimer(Some(m.hwnd), LOG_TIMER, LOG_POLL_MS, None) };
        });
        Ok(())
    }

    fn create(log_path: &Path) -> Result<MainWindow, String> {
        unsafe {
            let controls = INITCOMMONCONTROLSEX {
                dwSize: std::mem::size_of::<INITCOMMONCONTROLSEX>() as u32,
                dwICC: ICC_TAB_CLASSES | ICC_LISTVIEW_CLASSES,
            };
            let _ = InitCommonControlsEx(&controls);
            let instance = GetModuleHandleW(None).map_err(|e| e.to_string())?;
            let class = WNDCLASSEXW {
                cbSize: std::mem::size_of::<WNDCLASSEXW>() as u32,
                lpfnWndProc: Some(wndproc),
                hInstance: instance.into(),
                hCursor: LoadCursorW(None, IDC_ARROW).unwrap_or_default(),
                hbrBackground: HBRUSH((COLOR_BTNFACE.0 + 1) as usize as *mut _),
                lpszClassName: w!("EdOverlayMain"),
                ..Default::default()
            };
            RegisterClassExW(&class);
            let title = wide(TITLE);
            let hwnd = CreateWindowExW(
                WINDOW_EX_STYLE::default(),
                w!("EdOverlayMain"),
                PCWSTR(title.as_ptr()),
                WS_OVERLAPPEDWINDOW | WS_CLIPCHILDREN,
                CW_USEDEFAULT,
                CW_USEDEFAULT,
                CW_USEDEFAULT,
                CW_USEDEFAULT,
                None,
                None,
                Some(instance.into()),
                None,
            )
            .map_err(|e| e.to_string())?;
            let dpi = GetDpiForWindow(hwnd).max(96) as i32;
            let _ = SetWindowPos(hwnd, None, 0, 0, 960 * dpi / 96, 640 * dpi / 96, SWP_NOZORDER | SWP_NOACTIVATE | SWP_NOMOVE);
            let tabs = CreateWindowExW(
                WINDOW_EX_STYLE::default(),
                WC_TABCONTROLW,
                PCWSTR::null(),
                WS_CHILD | WS_VISIBLE | WS_CLIPSIBLINGS | WS_TABSTOP,
                0,
                0,
                0,
                0,
                Some(hwnd),
                None,
                Some(instance.into()),
                None,
            )
            .map_err(|e| e.to_string())?;
            let edit = CreateWindowExW(
                WS_EX_CLIENTEDGE,
                w!("EDIT"),
                PCWSTR::null(),
                WS_CHILD
                    | WS_VISIBLE
                    | WS_VSCROLL
                    | WS_TABSTOP
                    | WINDOW_STYLE((ES_MULTILINE | ES_AUTOVSCROLL | ES_READONLY | ES_NOHIDESEL) as u32),
                0,
                0,
                0,
                0,
                Some(hwnd),
                None,
                Some(instance.into()),
                None,
            )
            .map_err(|e| e.to_string())?;
            send(edit, EM_SETLIMITTEXT, 0x7FFF_FFFE, 0);
            let regions = RegionsView::create(hwnd, instance.into())?;
            let window = MainWindow {
                hwnd,
                tabs,
                pages: vec![edit, regions.list],
                log: LogView { edit, path: log_path.to_path_buf(), offset: 0, pending: Vec::new(), chars: 0 },
                regions,
                fonts: Fonts::new(dpi),
            };
            window.add_tab(0, "Log");
            window.add_tab(REGIONS_TAB as usize, "Regions");
            window.apply_fonts();
            window.layout();
            let _ = ShowWindow(hwnd, SW_SHOWNOACTIVATE);
            Ok(window)
        }
    }

    fn add_tab(&self, index: usize, label: &str) {
        let mut text = wide(label);
        let item = TCITEMW { mask: TCIF_TEXT, pszText: PWSTR(text.as_mut_ptr()), ..Default::default() };
        send(self.tabs, TCM_INSERTITEMW, index, &item as *const TCITEMW as isize);
    }

    fn apply_fonts(&self) {
        send(self.tabs, WM_SETFONT, self.fonts.ui.0 as usize, 1);
        send(self.log.edit, WM_SETFONT, self.fonts.mono.0 as usize, 1);
        send(self.regions.list, WM_SETFONT, self.fonts.ui.0 as usize, 1);
        self.regions.autosize();
    }

    fn layout(&self) {
        let mut client = RECT::default();
        unsafe {
            let _ = GetClientRect(self.hwnd, &mut client);
            let _ = MoveWindow(self.tabs, 0, 0, client.right, client.bottom, true);
        }
        let mut page = client;
        send(self.tabs, TCM_ADJUSTRECT, 0, &mut page as *mut RECT as isize);
        for &p in &self.pages {
            unsafe {
                let _ = MoveWindow(p, page.left, page.top, page.right - page.left, page.bottom - page.top, true);
            }
        }
    }

    fn show_selected(&self) {
        let selected = send(self.tabs, TCM_GETCURSEL, 0, 0);
        if selected == REGIONS_TAB {
            REGIONS_WANTED.set(true);
        }
        for (i, &p) in self.pages.iter().enumerate() {
            unsafe {
                let _ = ShowWindow(p, if i as isize == selected { SW_SHOW } else { SW_HIDE });
            }
        }
    }

    fn dpi_changed(&mut self, suggested: &RECT) {
        let dpi = unsafe { GetDpiForWindow(self.hwnd) }.max(96) as i32;
        self.fonts = Fonts::new(dpi);
        self.apply_fonts();
        unsafe {
            let _ = SetWindowPos(
                self.hwnd,
                None,
                suggested.left,
                suggested.top,
                suggested.right - suggested.left,
                suggested.bottom - suggested.top,
                SWP_NOZORDER | SWP_NOACTIVATE,
            );
        }
        self.layout();
    }
}

fn with_main(f: impl FnOnce(&mut MainWindow)) -> bool {
    MAIN.with(|cell| match cell.try_borrow_mut() {
        Ok(mut guard) => match guard.as_mut() {
            Some(m) => {
                f(m);
                true
            }
            None => false,
        },
        Err(_) => false,
    })
}

unsafe extern "system" fn wndproc(hwnd: HWND, msg: u32, wparam: WPARAM, lparam: LPARAM) -> LRESULT {
    match msg {
        WM_SIZE => {
            with_main(|m| m.layout());
            LRESULT(0)
        }
        WM_TIMER if wparam.0 == LOG_TIMER => {
            with_main(|m| m.log.poll());
            LRESULT(0)
        }
        WM_NOTIFY => {
            let header = unsafe { &*(lparam.0 as *const NMHDR) };
            if header.code == TCN_SELCHANGE {
                with_main(|m| m.show_selected());
            } else if header.code == LVN_COLUMNCLICK {
                let column = unsafe { (*(lparam.0 as *const NMLISTVIEW)).iSubItem };
                with_main(|m| m.regions.sort_by(column as usize));
            }
            LRESULT(0)
        }
        WM_DPICHANGED => {
            let suggested = unsafe { *(lparam.0 as *const RECT) };
            with_main(|m| m.dpi_changed(&suggested));
            LRESULT(0)
        }
        WM_DESTROY => {
            unsafe {
                let _ = KillTimer(Some(hwnd), LOG_TIMER);
                PostQuitMessage(0);
            }
            LRESULT(0)
        }
        _ => unsafe { DefWindowProcW(hwnd, msg, wparam, lparam) },
    }
}
