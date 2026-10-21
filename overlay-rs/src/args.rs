use std::path::PathBuf;

use clap::Parser;

#[derive(Parser, Clone, Debug)]
#[command(name = "ed-overlay", about = "Top-10 rare-object predictions in the CURRENT SECTOR.")]
pub struct Args {
    #[arg(long, default_value_os_t = crate::journal::default_dir(), help = "Elite's saved-games directory")]
    pub journal_dir: PathBuf,
    #[arg(long, help = "window x (default: pinned to the left screen edge)")]
    pub x: Option<i32>,
    #[arg(long, help = "window y (default: pinned to the top screen edge)")]
    pub y: Option<i32>,
    #[arg(long, default_value_t = 11, help = "base font size in points")]
    pub font: i32,
    #[arg(long, default_value_t = 0.85, help = "0.0-1.0 window opacity")]
    pub opacity: f64,
    #[arg(long, default_value_t = 2.0, help = "seconds between journal polls")]
    pub poll: f64,
    #[arg(
        long,
        default_value_t = 30.0,
        value_name = "SECONDS",
        help = "release the app-state database after this many idle seconds, so etl/ can write it"
    )]
    pub model_idle: f64,
    #[arg(
        long,
        default_value_t = 250,
        value_name = "MS",
        allow_negative_numbers = true,
        help = "log a breakdown for any tick slower than this (0 logs every tick, -1 switches timing off)"
    )]
    pub slow_ms: i64,
    #[arg(long, help = "never play the confirm chime or the clipboard tick (the flash still runs)")]
    pub no_sound: bool,
    #[arg(long, help = "do not drive the VKB throttle LEDs")]
    pub no_lights: bool,
    #[arg(long, help = "do not register the global navigation keys")]
    pub no_hotkeys: bool,
    #[arg(long, help = "do not hide the overlay when Elite loses focus")]
    pub always_visible: bool,
    #[arg(long, help = "show the title bar, status line and footer (default: table only)")]
    pub chrome: bool,
    #[arg(long, help = "do not allow dragging the window")]
    pub fixed: bool,
    #[arg(long, help = "show this sector and ignore the journal (for testing)")]
    pub sector: Option<String>,
    #[arg(long, help = "print one line per step of the reveal path")]
    pub trace: bool,
    #[arg(
        long,
        value_name = "FILE",
        help = "the commander's app-state database (default: state.duckdb in the data directory, created from \
                the bundled snapshot on first run)"
    )]
    pub state: Option<PathBuf>,
    #[arg(long, value_name = "FILE", help = "where the run log goes (default: overlay.log in the data directory)")]
    pub log: Option<PathBuf>,
    #[arg(long, hide = true, help = "print every table one repaint would show, as JSON, and exit")]
    pub dump: bool,
    #[arg(long, hide = true, num_args = 3, value_names = ["X", "Y", "Z"], allow_negative_numbers = true)]
    pub pos: Option<Vec<f64>>,
    #[arg(long, hide = true, num_args = 3, value_names = ["X", "Y", "Z"], allow_negative_numbers = true)]
    pub chain_to: Option<Vec<f64>>,
    #[arg(long, hide = true, default_value_t = 500.0)]
    pub range: f64,
    #[arg(long, hide = true, default_value_t = 75.0)]
    pub plain_range: f64,
}
