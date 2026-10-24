#![cfg_attr(not(test), windows_subsystem = "windows")]

mod alien;
mod app;
mod args;
mod bundle;
mod database;
mod dbworker;
mod dump;
mod engineers;
mod sirius;
mod journal;
mod jump;
mod lookup;
mod kdtree;
mod kinds;
mod lights;
mod log;
mod market;
mod names;
mod neutron_route;
mod route;
mod row;
mod ship;
mod table;
mod theme;
mod timing;
mod trace;
mod win;

use std::cell::RefCell;
use std::path::PathBuf;

use clap::Parser;
use windows::Win32::Foundation::{HWND, LPARAM, LRESULT, WPARAM};
use windows::Win32::System::Console::{ATTACH_PARENT_PROCESS, AttachConsole};
use windows::Win32::UI::HiDpi::{DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2, SetProcessDpiAwarenessContext};
use windows::Win32::UI::WindowsAndMessaging::{
    DispatchMessageW, GetMessageW, MA_NOACTIVATE, MB_ICONERROR, MB_OK, MSG, MessageBoxW, PostQuitMessage,
    TranslateMessage, WM_DESTROY, WM_DPICHANGED, WM_ERASEBKGND, WM_LBUTTONDOWN, WM_LBUTTONUP, WM_MOUSEACTIVATE,
    WM_MOUSEMOVE, WM_PAINT, WM_TIMER,
};
use windows::core::PCWSTR;

use crate::app::App;
use crate::args::Args;
use crate::dbworker::DbWorker;
use crate::theme::Role;
use crate::win::main_window::MainWindow;
use crate::win::overlay::{Overlay, Pane, TICK_TIMER};

thread_local! {
    static APP: RefCell<Option<App>> = const { RefCell::new(None) };
}

fn with_app(f: impl FnOnce(&mut App)) -> bool {
    APP.with(|cell| match cell.try_borrow_mut() {
        Ok(mut guard) => match guard.as_mut() {
            Some(app) => {
                f(app);
                true
            }
            None => false,
        },
        Err(_) => false,
    })
}

unsafe extern "system" fn wndproc(hwnd: HWND, msg: u32, wparam: WPARAM, lparam: LPARAM) -> LRESULT {
    match msg {
        WM_TIMER => {
            with_app(|a| {
                if wparam.0 == TICK_TIMER {
                    let outcome = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| a.tick()));
                    if let Err(p) = outcome {
                        a.note(&format!("tick error: {}", dbworker::panic_text(&p)), Role::Warn);
                    }
                } else {
                    a.step_flash();
                }
            });
            LRESULT(0)
        }
        WM_PAINT => {
            if with_app(|a| a.pane(hwnd).paint(&a.scene())) {
                LRESULT(0)
            } else {
                Overlay::default_proc(hwnd, msg, wparam, lparam)
            }
        }
        WM_ERASEBKGND => LRESULT(1),
        WM_MOUSEACTIVATE => LRESULT(MA_NOACTIVATE as isize),
        WM_LBUTTONDOWN => {
            with_app(|a| a.pane_mut(hwnd).mouse_down());
            LRESULT(0)
        }
        WM_MOUSEMOVE => {
            with_app(|a| a.pane_mut(hwnd).mouse_move());
            LRESULT(0)
        }
        WM_LBUTTONUP => {
            with_app(|a| a.pane_mut(hwnd).mouse_up());
            LRESULT(0)
        }
        WM_DPICHANGED => {
            with_app(|a| a.dpi_changed());
            LRESULT(0)
        }
        WM_DESTROY => {
            unsafe { PostQuitMessage(0) };
            LRESULT(0)
        }
        _ => Overlay::default_proc(hwnd, msg, wparam, lparam),
    }
}

fn fail(text: &str) -> ! {
    say!("{text}");
    let body: Vec<u16> = text.encode_utf16().chain(std::iter::once(0)).collect();
    let title: Vec<u16> = "ed-overlay".encode_utf16().chain(std::iter::once(0)).collect();
    unsafe {
        MessageBoxW(None, PCWSTR(body.as_ptr()), PCWSTR(title.as_ptr()), MB_OK | MB_ICONERROR);
    }
    log::stop();
    std::process::exit(1);
}

fn main() {
    unsafe {
        let _ = AttachConsole(ATTACH_PARENT_PROCESS);
        let _ = SetProcessDpiAwarenessContext(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2);
    }
    let args = Args::parse();
    let data = bundle::data_dir();
    let log_path = args.log.clone().unwrap_or_else(|| data.join("overlay.log"));
    if let Err(e) = log::start(&log_path) {
        eprintln!("cannot open the log {}: {e}", log_path.display());
    }
    std::panic::set_hook(Box::new(|info| say!("PANIC {info}")));
    kinds::assert_vocabulary();
    theme::assert_columns_cover_kinds();
    trace::enable(args.trace);
    crate::trace!("start", argv = std::env::args().skip(1).collect::<Vec<_>>().join(" "));

    let model = bundle::extract(&data).unwrap_or_else(|e| fail(&format!("cannot unpack the bundled model: {e}")));
    let state = resolve_state(&args, &data, &model);
    say!("log: {}", log_path.display());
    say!("model: {} (bundle {})", model.display(), bundle::id());
    say!("state: {}", state.display());

    if args.dump {
        let outcome = dump::run(&args, &state, &model);
        log::stop();
        if let Err(e) = outcome {
            eprintln!("{e}");
            std::process::exit(1);
        }
        return;
    }

    let worker = DbWorker::start(state, model, args.model_idle, args.slow_ms);
    let ui = Overlay::create(
        app::TITLE,
        args.font,
        args.opacity,
        (args.x, args.y),
        !args.fixed,
        args.chrome,
        Pane::Left,
        wndproc,
    )
    .unwrap_or_else(|e| fail(&format!("cannot create the overlay window: {e}")));
    let top = Overlay::create(
        app::TITLE,
        args.font,
        args.opacity,
        (None, None),
        !args.fixed,
        args.chrome,
        Pane::Top,
        wndproc,
    )
    .unwrap_or_else(|e| fail(&format!("cannot create the top overlay window: {e}")));
    MainWindow::open(&log_path).unwrap_or_else(|e| fail(&format!("cannot create the main window: {e}")));
    APP.with(|cell| *cell.borrow_mut() = Some(App::new(args, worker, ui, top)));
    with_app(|a| {
        a.run_startup();
        a.ui.start_timer(TICK_TIMER, app::KEY_POLL_MS);
    });
    unsafe {
        let mut msg = MSG::default();
        while GetMessageW(&mut msg, None, 0, 0).as_bool() {
            let _ = TranslateMessage(&msg);
            DispatchMessageW(&msg);
        }
    }
    with_app(App::shutdown);
    log::stop();
}

fn resolve_state(args: &Args, data: &std::path::Path, model: &std::path::Path) -> PathBuf {
    if let Some(given) = &args.state {
        if !given.exists() {
            fail(&format!("app-state database not found: {}", given.display()));
        }
        return given.clone();
    }
    let state = data.join("state.duckdb");
    if !state.exists() {
        match database::create_state(&state, model) {
            Ok(n) => say!("created {} from the bundled snapshot ({n} rows)", state.display()),
            Err(e) => fail(&format!("cannot create the app-state database {}: {e}", state.display())),
        }
    }
    state
}
