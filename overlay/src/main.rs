#![cfg_attr(not(test), windows_subsystem = "windows")]

mod alien;
mod app;
mod args;
mod database;
mod dbworker;
mod dump;
mod engineers;
mod bands;
mod exobio;
mod fss;
mod sirius;
mod slots;
mod spectrum;
mod journal;
mod jump;
mod lookup;
mod kdtree;
mod kinds;
mod lights;
mod log;
mod carriers;
mod market;
mod names;
mod paths;
mod prefs;
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
    TranslateMessage, WM_DESTROY, WM_ERASEBKGND, WM_LBUTTONDOWN, WM_LBUTTONUP, WM_MOUSEACTIVATE,
    WM_MOUSEMOVE, WM_PAINT, WM_TIMER,
};
use windows::core::PCWSTR;

use crate::app::App;
use crate::args::Args;
use crate::dbworker::DbWorker;
use crate::fss::Fss;
use crate::win::main_window::MainWindow;
use crate::win::overlay::{HYPER_TIMER, Overlay, PULSE_TIMER, Pane, Style, TICK_TIMER};

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
                        a.note(&format!("tick error: {}", dbworker::panic_text(&p)));
                    }
                } else if wparam.0 == PULSE_TIMER {
                    a.step_pulse();
                } else if wparam.0 == HYPER_TIMER {
                    a.step_hyper();
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
            with_app(|a| a.dropped(hwnd));
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
    let title: Vec<u16> = "Explorers Companion".encode_utf16().chain(std::iter::once(0)).collect();
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
    let data = paths::data_dir();
    paths::adopt_legacy_data_dir();
    let log_path = args.log.clone().unwrap_or_else(paths::log_file);
    if let Err(e) = log::start(&log_path) {
        eprintln!("cannot open the log {}: {e}", log_path.display());
    }
    std::panic::set_hook(Box::new(|info| say!("PANIC {info}")));
    kinds::assert_vocabulary();
    theme::assert_columns_cover_kinds();
    trace::enable(args.trace);
    crate::trace!("start", argv = std::env::args().skip(1).collect::<Vec<_>>().join(" "));

    let seed = paths::default_seed();
    say!("log: {}", log_path.display());
    let state = resolve_state(&args, &data, &seed);
    say!("state: {}", state.display());

    if args.dump {
        let outcome = dump::run(&args, &state);
        log::stop();
        if let Err(e) = outcome {
            eprintln!("{e}");
            std::process::exit(1);
        }
        return;
    }

    load_settings(&state, &data);
    let worker = DbWorker::start(state, args.model_idle, args.slow_ms);
    let prefs = prefs::get();
    let game_h = win::screen::game_height().unwrap_or_else(win::screen::screen_height);
    say!("hud: {game_h} px high, scale {:.2}", win::overlay::hud_scale(game_h, prefs.size));
    let pane = |pane: Pane| {
        Overlay::create(Style::of(pane, &prefs, game_h), pane, wndproc)
            .unwrap_or_else(|e| fail(&format!("cannot create the {pane:?} overlay window: {e}")))
    };
    let ui = pane(Pane::Left);
    let top = pane(Pane::Top);
    let map = pane(Pane::Map);
    let plan = pane(Pane::Plan);
    let popup = pane(Pane::Popup);
    let marks_pane = pane(Pane::Marks);
    let system_pane = pane(Pane::System);
    let coords_pane = pane(Pane::Coords);
    MainWindow::open(&log_path).unwrap_or_else(|e| fail(&format!("cannot create the main window: {e}")));
    let fss = Fss::start(fss::CALIBRATE.then(paths::screenshot_dir));
    APP.with(|cell| *cell.borrow_mut() = Some(App::new(args, worker, fss, game_h, [ui, top, map, plan, popup, marks_pane, system_pane, coords_pane])));
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

fn load_settings(state: &std::path::Path, data: &std::path::Path) {
    let read = |import: &[(String, String)]| {
        database::load_settings(state, import).unwrap_or_else(|e| fail(&format!("cannot read the settings in {}: {e}", state.display())))
    };
    let mut saved = read(&[]);
    let legacy_path = data.join(paths::LEGACY_BINDINGS);
    let legacy = win::hotkeys::legacy_bindings(&legacy_path);
    if !legacy.is_empty() && !saved.keys().any(|k| k.starts_with(win::hotkeys::SETTING_PREFIX)) {
        saved = read(&legacy);
        say!("settings: imported {} key binding(s) from {}", legacy.len(), legacy_path.display());
    }
    for warning in win::hotkeys::apply_bindings(&saved) {
        say!("hotkeys: {warning}");
    }
    fss::set_keep_all(saved.get(fss::KEEP_SETTING).is_some_and(|v| v == "true"));
    let (chosen, mut warnings) = prefs::Prefs::from_settings(&saved);
    warnings.extend(prefs::load_places(&saved));
    for warning in warnings {
        say!("settings: {warning}");
    }
    prefs::set(chosen);
}

fn install(seed: &std::path::Path, state: &std::path::Path) -> Result<(), String> {
    say!("seed: {}", seed.display());
    match database::install(seed, state)? {
        database::Installed::Current => say!("{} already holds this seed", state.display()),
        database::Installed::Fresh => say!("installed {} from the seed", state.display()),
        database::Installed::Migrated { backup, rows, dropped } => {
            say!("installed {} from the seed and migrated {rows} commander rows from {}", state.display(), backup.display());
            if !dropped.is_empty() {
                say!("migration left behind column(s) the new schema has no place for: {}", dropped.join(", "));
            }
        }
    }
    Ok(())
}

fn resolve_state(args: &Args, data: &std::path::Path, seed: &std::path::Path) -> PathBuf {
    if let Some(given) = &args.state {
        if !given.exists() {
            fail(&format!("app-state database not found: {}", given.display()));
        }
        return given.clone();
    }
    let state = data.join(paths::STATE_FILE);
    if seed.exists() {
        if let Err(e) = install(seed, &state) {
            fail(&format!("cannot install the seed {}: {e}", seed.display()));
        }
    } else if !state.exists() {
        fail(&format!("no app-state database and no seed: put {} beside the exe", paths::SEED_FILE));
    }
    state
}
