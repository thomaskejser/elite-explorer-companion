use std::collections::{BTreeMap, HashMap, HashSet};
use std::time::{Instant, SystemTime};

use serde_json::Value;

use crate::args::Args;
use crate::database::{self, AliasOutcome, CarrierHop, CarrierView, ExoBodyRow, ExoSystemRow, TradeRow};
use crate::dbworker::{Answer, Ask, DbWorker, Only, Results};
use crate::exobio::{self, Here, Sheet};
use crate::journal::{self, Gated, Hop, JournalReader};
use crate::kinds::{self, KINDS};
use crate::lights::{self, Lights};
use crate::market::{Market, Quotes, Tritium};
use crate::names;
use crate::neutron_route::ChainHop;
use crate::route::{self, dist};
use crate::row::*;
use crate::say;
use crate::ship;
use crate::table::{TargetTable, light_years, thousands_i};
use crate::theme::{self, FLASH_CONFIRM, FLASH_COPIED, Role};
use crate::timing::Phases;
use crate::trace;
use crate::win::hotkeys::{self, Action};
use crate::jump::{self, Panel};
use crate::lookup::{Lookup, SystemInfo};
use crate::win::overlay::{FLASH_TIMER, Overlay, Scene};
use crate::win::main_window::{self, UiAsk};
use crate::win::{clipboard, focus, notify};

pub const TITLE: &str = "Explorers Companion";
const SECTOR_TITLE: &str = "Current sector";
const CONFIRMED_TITLE: &str = "Confirmed";
const NEAREST_TITLE: &str = "Nearest";
pub const ROWS: usize = 10;
const CARRIER_ROWS: i64 = 1;
const NEUTRON_ROWS: usize = 1;
const ROUTE_ROWS: usize = 2;
const ROUTE_ALIAS: [(&str, &str); 1] = [("Shinrarta Dezhra", "FOUNDER")];
const BOOSTED_LY: f64 = 500.0;
const CHAIN_SLACK: f64 = 1.0;
pub const UNFOUND_ROWS: i64 = 3;
const SUMMARY_ROWS: usize = 1;
const ADJACENT_ROWS: usize = 26;
const FSD_CHARGING: u64 = 1 << 17;
const GUI_STATION: u64 = 5;
const GUI_GALAXY_MAP: u64 = 6;
const GUI_SYSTEM_MAP: u64 = 7;
const GUI_FSS: u64 = 9;
const GUI_DSS: u64 = 10;
const GUI_HIDES_LEFT: [u64; 3] = [GUI_STATION, GUI_FSS, GUI_DSS];
const GUI_HIDES_TOP: [u64; 5] = [GUI_STATION, GUI_GALAXY_MAP, GUI_SYSTEM_MAP, GUI_FSS, GUI_DSS];
const GUI_HIDES_RIGHT: [u64; 4] = [GUI_STATION, GUI_GALAXY_MAP, GUI_FSS, GUI_DSS];
const REGION_ROWS: usize = 1;
pub const KEY_POLL_MS: u32 = 120;
const BINDINGS_FILE: &str = "keybindings.json";

const CONF: usize = 0;
const NEAR: usize = 1;
const SECT: usize = 2;

const SETTLED_BY_CLASS: [i64; 3] = [ROW_PREDICTED, ROW_CATALOG, ROW_SECTOR];
const RETIRED_BY_WRONG: [i64; 4] = [ROW_PREDICTED, ROW_CATALOG, ROW_SECTOR, ROW_UNFOUND];
const CARRIER_READY: Role = Role::Confirmed;
const CARRIER_JUMPING: Role = Role::Hot;
const CARRIER_COOLING: Role = Role::Neutron;
const ALIAS_SOURCE: [i64; 4] = [ROW_PREDICTED, ROW_CATALOG, ROW_SECTOR, ROW_UNFOUND];

fn wrong_source(grp: i64) -> Option<&'static str> {
    match grp {
        ROW_PREDICTED | ROW_CATALOG | ROW_SECTOR => Some("predicted"),
        ROW_UNFOUND => Some("unfound"),
        _ => None,
    }
}

struct Chain {
    hops: Vec<ChainHop>,
    range: f64,
    dest: String,
}

struct Follow {
    label: String,
}

struct PlottedDest {
    name: String,
    id64: Option<i64>,
    xyz: [Option<f64>; 3],
    star_class: Option<String>,
}

pub enum Then {
    Arrived,
    Solved { label: String, dest: String, rng: f64 },
    Paint { sector: Option<String> },
    Marked { system: String, sector: Option<String> },
    Aliased { system: String, canonical: String, sector: Option<String> },
    Revealed { finds: Vec<(String, String)>, note: Option<String>, sector: Option<String> },
    Routed { dest: String, dest_xyz: [f64; 3], rest: Vec<f64> },
    Counted,
    CaughtUp { harvested: usize },
    Regions,
    MapRegions,
    Sectors,
    Picked { sector: String, kind: &'static str },
    CarrierView { carrier: journal::Carrier },
    CarrierDestination,
    MapGrid,
    Trade,
    Outcomes,
    Exobio,
}

fn bindings_path() -> std::path::PathBuf {
    crate::bundle::data_dir().join(BINDINGS_FILE)
}

fn take_rows(r: &mut Results, name: &str) -> Option<Vec<Row>> {
    match r.remove(name) {
        Some(Answer::Rows(rows)) => Some(rows),
        Some(Answer::MaybeRows(rows)) => rows,
        _ => None,
    }
}

fn hop_xyz(h: &ChainHop) -> [f64; 3] {
    [h.x, h.y, h.z]
}

pub struct App {
    args: Args,
    timing: Phases,
    worker: DbWorker,
    market: Market,
    req: u64,
    pending: HashMap<u64, Then>,
    keyed: HashMap<String, u64>,
    reader: JournalReader,
    pub ui: Overlay,
    pub top: Overlay,
    pub right: Overlay,
    here: Here,
    exo_here: Vec<ExoBodyRow>,
    exo_target: Option<ExoSystemRow>,
    exo_target_for: Option<String>,
    exo_near: Vec<ExoSystemRow>,
    exo_sheets: Vec<Sheet>,
    lookup: Lookup,
    infos: HashMap<String, Option<SystemInfo>>,
    route_hops: Vec<Hop>,
    jump: Option<Panel>,
    next_jump_id64: Option<i64>,
    tables: [TargetTable; 3],
    clock_text: String,
    system: Option<String>,
    sector: Option<String>,
    crafted: bool,
    pos: Option<[f64; 3]>,
    rows: [Vec<Row>; 3],
    active: usize,
    cursor: usize,
    marks: HashMap<usize, String>,
    pending_flash: Option<String>,
    copied: Option<String>,
    dests: BTreeMap<String, (String, [f64; 3])>,
    chains: BTreeMap<String, Chain>,
    solving: HashSet<String>,
    unsolvable: HashMap<String, (String, i64)>,
    follow: Option<Follow>,
    carrier_rows: Option<Vec<Row>>,
    last_pick: Option<String>,
    carrier_target: Option<String>,
    carrier: Option<journal::Carrier>,
    carrier_hop: Option<CarrierHop>,
    carrier_line: [String; 3],
    carrier_role: Role,
    neutron_rows: Option<Vec<Row>>,
    route: Option<Vec<Row>>,
    route_dest: Option<String>,
    jump_range: Option<f64>,
    lights: Lights,
    loadout: Option<Value>,
    next_jump: Option<(String, Option<String>)>,
    plotted: Option<PlottedDest>,
    last_poll: Option<Instant>,
    navroute_mtime: Option<SystemTime>,
    status_mtime: Option<SystemTime>,
    status: Option<Value>,
    counts: BTreeMap<String, i64>,
    flash_running: bool,
}

impl App {
    pub fn new(args: Args, worker: DbWorker, ui: Overlay, top: Overlay, right: Overlay) -> App {
        let tables = [
            TargetTable::new(theme::confirmed_columns(), KINDS.len(), CONFIRMED_TITLE, true, true).untitled(),
            TargetTable::new(
                theme::nearest_columns(),
                CARRIER_ROWS as usize + NEUTRON_ROWS + ROUTE_ROWS,
                NEAREST_TITLE,
                true,
                false,
            )
            .untitled(),
            TargetTable::new(
                theme::sector_columns(),
                ROWS + UNFOUND_ROWS as usize + SUMMARY_ROWS + ADJACENT_ROWS + REGION_ROWS,
                SECTOR_TITLE,
                false,
                false,
            )
            .with_min_rows(ROWS + SUMMARY_ROWS + ADJACENT_ROWS + REGION_ROWS)
            .untitled(),
        ];
        let mut app = App {
            timing: Phases::new(args.slow_ms, ""),
            reader: JournalReader::new(args.journal_dir.clone()),
            lights: Lights::new(!args.no_lights),
            args,
            worker,
            market: Market::start(),
            req: 0,
            pending: HashMap::new(),
            keyed: HashMap::new(),
            ui,
            top,
            right,
            here: Here::default(),
            exo_here: Vec::new(),
            exo_target: None,
            exo_target_for: None,
            exo_near: Vec::new(),
            exo_sheets: Vec::new(),
            lookup: Lookup::start(),
            infos: HashMap::new(),
            route_hops: Vec::new(),
            jump: None,
            next_jump_id64: None,
            tables,
            clock_text: String::new(),
            system: None,
            sector: None,
            crafted: false,
            pos: None,
            rows: Default::default(),
            active: 0,
            cursor: 0,
            marks: HashMap::new(),
            pending_flash: None,
            copied: None,
            dests: BTreeMap::new(),
            chains: BTreeMap::new(),
            solving: HashSet::new(),
            unsolvable: HashMap::new(),
            follow: None,
            carrier_rows: None,
            last_pick: None,
            carrier_target: None,
            carrier: None,
            carrier_hop: None,
            carrier_line: Default::default(),
            carrier_role: Role::Carrier,
            neutron_rows: None,
            route: None,
            route_dest: None,
            jump_range: None,
            loadout: None,
            next_jump: None,
            plotted: None,
            last_poll: None,
            navroute_mtime: None,
            status_mtime: None,
            status: None,
            counts: BTreeMap::new(),
            flash_running: false,
        };
        app.recount();
        app
    }

    fn table_name(i: usize) -> &'static str {
        [CONFIRMED_TITLE, NEAREST_TITLE, SECTOR_TITLE][i]
    }

    pub fn scene(&self) -> Scene<'_> {
        Scene {
            confirmed: &self.tables[CONF],
            nearest: &self.tables[NEAR],
            sector: &self.tables[SECT],
            clock: &self.clock_text,
            carrier: &self.carrier_line,
            carrier_role: self.carrier_role,
            jump: self.jump.as_ref(),
            exobio: &self.exo_sheets,
        }
    }

    pub fn pane(&self, hwnd: windows::Win32::Foundation::HWND) -> &Overlay {
        if hwnd == self.top.hwnd {
            &self.top
        } else if hwnd == self.right.hwnd {
            &self.right
        } else {
            &self.ui
        }
    }

    pub fn pane_mut(&mut self, hwnd: windows::Win32::Foundation::HWND) -> &mut Overlay {
        if hwnd == self.top.hwnd {
            &mut self.top
        } else if hwnd == self.right.hwnd {
            &mut self.right
        } else {
            &mut self.ui
        }
    }

    fn redraw(&mut self) {
        let scene = Scene {
            confirmed: &self.tables[CONF],
            nearest: &self.tables[NEAR],
            sector: &self.tables[SECT],
            clock: &self.clock_text,
            carrier: &self.carrier_line,
            carrier_role: self.carrier_role,
            jump: self.jump.as_ref(),
            exobio: &self.exo_sheets,
        };
        self.ui.refresh(&scene);
        self.top.refresh(&scene);
        self.right.refresh(&scene);
        let flashing = self.tables.iter().any(TargetTable::flashing);
        if flashing && !self.flash_running {
            self.ui.start_timer(FLASH_TIMER, theme::FLASH_STEP_MS);
            self.flash_running = true;
        }
    }

    pub fn dpi_changed(&mut self) {
        self.ui.dpi_changed();
        self.top.dpi_changed();
        self.right.dpi_changed();
        self.redraw();
    }

    pub fn step_flash(&mut self) {
        for t in &mut self.tables {
            t.step_flash();
        }
        if !self.tables.iter().any(TargetTable::flashing) {
            self.ui.stop_timer(FLASH_TIMER);
            self.flash_running = false;
        }
        self.redraw();
    }

    fn ask(&mut self, asks: Vec<Ask>, then: Then, write: bool, key: Option<&str>) {
        self.req += 1;
        if let Some(k) = key
            && let Some(old) = self.keyed.insert(k.to_string(), self.req) {
                self.pending.remove(&old);
            }
        self.pending.insert(self.req, then);
        self.worker.submit(self.req, asks, write, key.map(String::from));
    }

    fn drain_db(&mut self) {
        for (req_id, payload) in self.worker.drain() {
            let Some(then) = self.pending.remove(&req_id) else { continue };
            match payload {
                Err(e) => self.note(&format!("database error: {e}"), Role::Warn),
                Ok(r) => {
                    let _p = self.timing.phase("db_result");
                    self.dispatch(then, r);
                }
            }
        }
    }

    fn dispatch(&mut self, then: Then, mut r: Results) {
        match then {
            Then::Arrived => self.arrived(r),
            Then::Solved { label, dest, rng } => self.solved(r, label, dest, rng),
            Then::Paint { sector } => self.paint_from(r, sector),
            Then::Marked { system, sector } => {
                self.recount();
                let fresh = matches!(r.remove("mark_wrong"), Some(Answer::Bool(true)));
                self.note(
                    &format!("{system}: marked as not existing{}", if fresh { "" } else { " (already marked)" }),
                    Role::Warn,
                );
                self.paint_from(r, sector);
            }
            Then::Aliased { system, canonical, sector } => {
                let text = match r.remove("record_alias") {
                    Some(Answer::Alias(AliasOutcome::Recorded)) => format!("aliased: {system} = {canonical}"),
                    Some(Answer::Alias(AliasOutcome::HeldBy(held))) => {
                        format!("not aliased: {canonical} is already the rename of {held}")
                    }
                    _ => format!("aliased: {system} = {canonical} (unchanged)"),
                };
                self.note(&text, Role::Ok);
                self.paint_from(r, sector);
            }
            Then::Revealed { finds, note, sector } => self.revealed(r, finds, note, sector),
            Then::Routed { dest, dest_xyz, rest } => self.routed(r, dest, dest_xyz, rest),
            Then::Counted => {
                if let Some(Answer::Counts(c)) = r.remove("counts") {
                    self.counts = c;
                }
                self.update_status();
            }
            Then::CaughtUp { harvested } => self.caught_up(r, harvested),
            Then::Regions => {
                if let Some(Answer::Regions(rows)) = r.remove("region_expected") {
                    let _p = self.timing.phase("regions_fill");
                    main_window::show_regions(rows);
                }
            }
            Then::MapRegions => {
                if let Some(Answer::Regions(rows)) = r.remove("region_expected") {
                    main_window::show_map_regions(rows);
                }
            }
            Then::Picked { sector, kind } => {
                match r.remove("sector_best") {
                    Some(Answer::Pick(Some((system, p)))) => {
                        let chance = p.map_or(String::new(), |p| format!(" ({:.1}%)", 100.0 * p));
                        self.last_pick = Some(system.clone());
                        if crate::win::clipboard::copy(&system) {
                            say!("{sector}: {system} has the best chance of {kind}{chance} -- copied to the clipboard");
                        }
                    }
                    _ => say!("{sector}: no unvisited prediction left to copy"),
                }
            }
            Then::CarrierView { mut carrier } => {
                let view = match r.remove("carrier_view") {
                    Some(Answer::Carrier(view)) => *view,
                    _ => CarrierView { pos: carrier.pos, hop: None },
                };
                carrier.pos = view.pos;
                self.carrier = Some(carrier);
                self.carrier_hop = view.hop;
                self.show_carrier();
            }
            Then::CarrierDestination => {
                if let Some(Answer::Text(Some(destination))) = r.remove("carrier_destination") {
                    self.carrier_target = Some(destination);
                }
                self.refresh_carrier();
            }
            Then::Sectors => {
                if let Some(Answer::Regions(rows)) = r.remove("sector_expected") {
                    main_window::show_sectors(rows);
                }
            }
            Then::Outcomes => self.took_outcomes(r),
            Then::Exobio => self.took_exobio(r),
            Then::Trade => {
                if let Some(Answer::Trade(rows)) = r.remove("trade_targets") {
                    main_window::show_trade(rows);
                }
            }
            Then::MapGrid => {
                if let Some(Answer::Map(grid)) = r.remove("map_grid") {
                    let _p = self.timing.phase("map_grid");
                    main_window::show_map_grid(*grid);
                }
            }
        }
    }

    fn on_position(&mut self, event: &Value, record: bool) {
        let p = journal::position_of(event);
        let Some(system) = p.system else { return };
        self.system = Some(system.clone());
        let moved = p.xyz.is_some() && p.xyz != self.pos;
        if moved {
            self.pos = p.xyz;
            self.ask_trade();
            if let Some(pos) = self.pos {
                self.market.request(pos);
                main_window::show_tritium(Quotes::all(Tritium::Searching));
            }
        }
        if record {
            self.advance_route(&system);
            self.advance_follow(&system);
        }
        self.solve_chains();
        if record {
            let asks = vec![
                Ask::RecordArrival { system: system.clone(), ts: p.timestamp.clone() },
                Ask::OutcomeVisit { system: system.clone(), ts: p.timestamp },
                Ask::Outcomes,
            ];
            self.ask(asks, Then::Arrived, true, None);
        }
        self.ask_exobio_nearby();
        let parsed = names::sector_of(&system);
        self.crafted = parsed.is_none();
        let sector = parsed.unwrap_or_else(|| names::CRAFTED_SECTOR.to_string());
        if Some(&sector) != self.sector.as_ref() || moved {
            self.sector = Some(sector);
            self.refresh(true);
        }
        self.update_status();
    }

    fn dress_nearest(&self, mut rows: Vec<Row>) -> Vec<Row> {
        let chain = self.chains.get("CARRIER").map(|c| &c.hops);
        for row in &mut rows {
            let arrived = self.system.is_some() && row.system == self.system;
            if row.grp() == ROW_CARRIER && !arrived
                && let Some(hops) = chain
                    && let Some(target) = self.chain_target(hops) {
                        row.system = Some(target.system.clone());
                        row.jumps = Some(Self::hops_left(hops, target.hop));
                        row.x = Some(target.x);
                        row.y = Some(target.y);
                        row.z = Some(target.z);
                        row.dist_ly = self.pos.map(|p| dist(&p, &hop_xyz(target)));
                    }
            if row.jumps.is_none() {
                let reach = if row.grp() == ROW_NEUTRON { self.jump_range } else { Some(self.boosted_range()) };
                row.jumps = match (row.dist_ly, reach) {
                    (Some(ly), Some(r)) if r != 0.0 => Some((ly / r).ceil() as i64),
                    _ => None,
                };
            }
            if row.grp() == ROW_CARRIER && arrived {
                row.arrived_text = row.wide_text.clone();
            }
        }
        rows
    }

    fn boosted_range(&self) -> f64 {
        match self.jump_range {
            Some(r) if r != 0.0 => r * ship::neutron_boost(self.loadout.as_ref()),
            _ => BOOSTED_LY,
        }
    }

    fn chain_targets(&self) -> BTreeMap<String, (String, [f64; 3])> {
        let mut out = self.dests.clone();
        if let Some(row) = self.carrier_rows.as_ref().and_then(|r| r.first())
            && let (Some(xyz), Some(sys)) = (row.xyz(), row.system.clone()) {
                out.insert("CARRIER".into(), (sys, xyz));
            }
        out
    }

    fn chain_stale(&self, label: &str, dest: &str) -> bool {
        let Some(chain) = self.chains.get(label) else { return true };
        if chain.dest != dest {
            return true;
        }
        if (chain.range - self.boosted_range()).abs() > 1.0 {
            return true;
        }
        let Some(pos) = self.pos else { return false };
        let reach = self.boosted_range() * CHAIN_SLACK;
        !chain.hops.iter().any(|h| dist(&pos, &hop_xyz(h)) <= reach)
    }

    fn solve_chains(&mut self) {
        let Some(pos) = self.pos else { return };
        for (label, (dest, xyz)) in self.chain_targets() {
            if self.solving.contains(&label) || !self.chain_stale(&label, &dest) {
                continue;
            }
            if Some(&dest) == self.system.as_ref() {
                self.chains.remove(&label);
                continue;
            }
            let rng = self.boosted_range();
            if self.unsolvable.get(&label) == Some(&(dest.clone(), rng.round() as i64)) {
                continue;
            }
            self.solving.insert(label.clone());
            let here = self.system.clone().unwrap_or_else(|| "here".into());
            let key = format!("solve:{label}");
            self.ask(
                vec![Ask::SolveRoute { origin: pos, dest: xyz, jump_ly: rng, names: (here, dest.clone()) }],
                Then::Solved { label, dest, rng },
                false,
                Some(&key),
            );
        }
    }

    fn solved(&mut self, mut r: Results, label: String, dest: String, rng: f64) {
        self.solving.remove(&label);
        let hops = match r.remove("solve_route") {
            Some(Answer::Chain(Some(h))) if !h.is_empty() => h,
            _ => {
                self.note(
                    &format!(
                        "no neutron chain to {dest} at {} ly boosted -- not retried until the ship or the \
                         destination changes",
                        light_years(rng)
                    ),
                    Role::Warn,
                );
                self.chains.remove(&label);
                self.unsolvable.insert(label, (dest, rng.round() as i64));
                return;
            }
        };
        self.unsolvable.remove(&label);
        let jumps = hops.len() - 1;
        self.chains.insert(label.clone(), Chain { hops, range: rng, dest: dest.clone() });
        self.note(&format!("{label}: {jumps} jump(s) to {dest} at {} ly boosted", light_years(rng)), Role::Ok);
        self.refresh(false);
    }

    fn route_rows(&self) -> Vec<Row> {
        let mut rows = Vec::new();
        for (label, chain) in &self.chains {
            if label == "CARRIER" {
                continue;
            }
            let Some(target) = self.chain_target(&chain.hops) else { continue };
            let following = self.follow.as_ref().is_some_and(|f| &f.label == label);
            rows.push(Row {
                system: Some(target.system.clone()),
                type_label: Some(label.clone()),
                dist_ly: self.pos.map(|p| dist(&p, &hop_xyz(target))),
                row_grp: Some(ROW_ROUTE),
                jumps: Some(Self::hops_left(&chain.hops, target.hop)),
                detail: Some(format!("{}{}", if following { "following " } else { "" }, chain.dest)),
                x: Some(target.x),
                y: Some(target.y),
                z: Some(target.z),
                route: Some(label.clone()),
                ..Row::default()
            });
        }
        rows
    }

    fn hops_left(hops: &[ChainHop], hop: i64) -> i64 {
        ((hops.len() as i64 - 1) - hop).abs() + 1
    }

    fn chain_target<'a>(&self, hops: &'a [ChainHop]) -> Option<&'a ChainHop> {
        let Some(pos) = self.pos else { return hops.first() };
        let goal = hop_xyz(hops.last()?);
        let here = dist(&pos, &goal);
        let ahead: Vec<&ChainHop> = hops.iter().filter(|h| dist(&hop_xyz(h), &goal) < here).collect();
        if ahead.is_empty() {
            return None;
        }
        let reach = self.boosted_range();
        let away = |h: &&ChainHop| dist(&pos, &hop_xyz(h));
        let near: Vec<&ChainHop> = ahead.iter().copied().filter(|h| away(h) <= reach).collect();
        let pool = if near.is_empty() { ahead } else { near };
        pool.into_iter().fold(None, |best: Option<&ChainHop>, h| match best {
            Some(b) if away(&b) <= away(&h) => Some(b),
            _ => Some(h),
        })
    }

    fn follow_route(&mut self, row: &Row) {
        let label = row.route.clone().or_else(|| (row.grp() == ROW_CARRIER).then(|| "CARRIER".to_string()));
        let Some(label) = label else { return };
        let next = row.system.clone().unwrap_or_default();
        let dest = self.chain_dest(&label);
        self.follow = Some(Follow { label });
        self.note(&format!("following the chain to {dest} -- next {next}. Copy any other row to stop."), Role::Ok);
    }

    fn chain_dest(&self, label: &str) -> String {
        self.chains.get(label).map_or_else(|| label.to_string(), |c| c.dest.clone())
    }

    fn advance_follow(&mut self, system: &str) -> bool {
        let Some(follow) = &self.follow else { return false };
        let Some(chain) = self.chains.get(&follow.label) else { return false };
        let Some(at) = chain.hops.iter().find(|h| h.system == system) else { return false };
        let at_hop = at.hop;
        let Some(nxt) = chain.hops.iter().find(|h| h.hop == at_hop + 1).cloned() else {
            let dest = chain.dest.clone();
            self.note(&format!("arrived at {dest} -- chain complete"), Role::Ok);
            self.follow = None;
            return false;
        };
        let left = Self::hops_left(&chain.hops, nxt.hop);
        if !clipboard::copy(&nxt.system) {
            self.note(&format!("could not reach the clipboard ({})", nxt.system), Role::Warn);
            return false;
        }
        self.took_clipboard(&nxt.system);
        self.note(&format!("hop {at_hop} flown -- copied {}, {left} to go", nxt.system), Role::Ok);
        true
    }

    fn arrived(&mut self, mut r: Results) {
        self.recount();
        if let Some(Answer::Arrival(Some(poi))) = r.remove("record_arrival") {
            self.note(&format!("POI logged here: {poi}"), Role::Ok);
        }
        if let Some(Answer::Count(1)) = r.remove("outcome_visit") {
            say!("prediction recorded for this visit; its outcome follows your scans (Settings tab)");
        }
        self.took_outcomes(r);
    }

    fn nearest_confirmed(confirmed: &[Row]) -> String {
        let located: Vec<&Row> = confirmed.iter().filter(|r| r.dist_ly.is_some()).collect();
        let Some(row) = located.into_iter().fold(None, |best: Option<&Row>, r| match best {
            Some(b) if b.dist_ly <= r.dist_ly => Some(b),
            _ => Some(r),
        }) else {
            return if confirmed.is_empty() { "none".into() } else { "distance unknown".into() };
        };
        format!(
            "{} ly ({})",
            light_years(row.dist_ly.unwrap_or(0.0)),
            row.type_label.clone().unwrap_or_default()
        )
    }

    pub fn note(&mut self, text: &str, role: Role) {
        let _p = self.timing.phase("p_note");
        self.ui.set_footer(text, role);
        if self.ui.chrome {
            self.redraw();
        } else {
            say!("{text}");
        }
    }

    fn update_clock(&mut self) {
        let text = local_hh_mm();
        if text != self.clock_text {
            self.clock_text = text;
            self.redraw();
        }
        let now = now_secs();
        let line = self
            .carrier
            .as_ref()
            .map_or(Default::default(), |c| journal::carrier_line(c, now, self.carrier_target.as_deref()));
        let role = match &self.carrier {
            None => Role::Carrier,
            Some(c) if c.pending.is_some() => CARRIER_JUMPING,
            Some(c) if journal::carrier_ready(c, now) => CARRIER_READY,
            Some(_) => CARRIER_COOLING,
        };
        if line != self.carrier_line || role != self.carrier_role {
            self.carrier_line = line;
            self.carrier_role = role;
            self.show_carrier();
            self.redraw();
        }
    }

    fn read_asks(&self, moved: bool) -> Vec<Ask> {
        let pos = self.pos;
        let mut asks = vec![Ask::ConfirmedTargets { pos }];
        if moved || self.carrier_rows.is_none() {
            asks.push(Ask::CarrierTargets { pos, limit: CARRIER_ROWS });
        }
        if moved || self.neutron_rows.is_none() {
            asks.push(Ask::NeutronTargets { pos, limit: NEUTRON_ROWS as i64 });
        }
        asks.push(Ask::AdjacentSectors { pos });
        if let Some(sector) = self.sector.clone() {
            asks.push(Ask::TopTargets { sector: sector.clone(), limit: ROWS as i64, pos });
            asks.push(Ask::UnfoundTargets { sector: sector.clone(), limit: UNFOUND_ROWS, pos });
            asks.push(Ask::SectorTotals { sector: sector.clone() });
            asks.push(Ask::RegionTotals { sector: sector.clone(), pos });
            asks.push(Ask::SectorSummary { sector });
        }
        asks
    }

    fn rebound(&mut self, rebound: hotkeys::Rebound) {
        match rebound {
            hotkeys::Rebound::Cancelled(action) => {
                say!("hotkeys: kept {} for {}", hotkeys::binding(action), hotkeys::description(action));
            }
            hotkeys::Rebound::Set { action, chord, swapped } => {
                say!("hotkeys: {chord} -> {}", hotkeys::description(action));
                if let Some(other) = swapped {
                    say!("hotkeys: {} -> {} (it was {chord})", hotkeys::binding(other), hotkeys::description(other));
                }
                if let Err(e) = hotkeys::save_bindings(&bindings_path()) {
                    say!("hotkeys: could not save {}: {e}", bindings_path().display());
                }
                self.redraw();
            }
        }
        main_window::refresh_settings();
    }

    fn took_outcomes(&mut self, mut r: Results) {
        if let Some(Answer::Outcomes(rows)) = r.remove("outcomes") {
            main_window::show_outcomes(rows);
        }
    }

    fn ask_trade(&mut self) {
        if let Some(pos) = self.pos {
            self.ask(vec![Ask::TradeTargets { pos }], Then::Trade, false, Some("trade"));
        }
        self.show_engineers();
    }

    fn refresh_carrier(&mut self) {
        let carrier = journal::read_carrier(&self.args.journal_dir, now_secs());
        let Some(system) = carrier.system.clone() else {
            self.carrier = Some(carrier);
            self.carrier_hop = None;
            self.show_carrier();
            return;
        };
        self.ask(
            vec![Ask::CarrierView {
                system,
                system_id: carrier.address,
                pos: carrier.pos,
                target: self.carrier_target.clone(),
            }],
            Then::CarrierView { carrier },
            false,
            Some("carrier_view"),
        );
    }

    fn show_carrier(&self) {
        let rows = match &self.carrier {
            Some(c) => self.carrier_rows_for(c, self.carrier_target.as_deref(), self.carrier_hop.clone()),
            None => Vec::new(),
        };
        main_window::show_carrier(rows);
    }

    fn carrier_rows_for(&self, c: &journal::Carrier, target: Option<&str>, hop: Option<CarrierHop>) -> Vec<TradeRow> {
        let row = |kind: &str, system: String, station: String, dist_ly: Option<f64>, note: String| TradeRow {
            kind: kind.to_string(),
            system,
            station,
            dist_ly,
            arrival_ls: None,
            note: Some(note),
        };
        let Some(system) = c.system.clone() else {
            return vec![row("Carrier", String::new(), String::new(), None, "no CarrierLocation in the recent journals".into())];
        };
        let label = match (&c.name, &c.callsign) {
            (Some(n), Some(cs)) => format!("{n} ({cs})"),
            (n, cs) => n.clone().or(cs.clone()).unwrap_or_default(),
        };
        let mut status = journal::carrier_phase(c, now_secs());
        status += &match (c.fuel, &c.stats_at) {
            (Some(f), Some(at)) => format!("  \u{00B7}  Tritium {f} t, read {}", at.replace('T', " ").trim_end_matches('Z')),
            _ => "  \u{00B7}  Tritium unknown: open carrier management to log it".to_string(),
        };
        if c.pos.is_none() {
            status += "  \u{00B7}  position unknown: no coordinates for this system";
        }
        let to_ship = c.pos.zip(self.pos).map(|(a, b)| crate::route::dist(&a, &b));
        let mut rows = vec![row("Carrier", system, label, to_ship, status)];
        let Some(target) = target else {
            rows.push(row("Destination", String::new(), String::new(), None,
                "click a sector on the Map tab, then press Carrier Route".into()));
            return rows;
        };
        let Some(hop) = hop else {
            rows.push(row("Destination", target.to_string(), String::new(), None,
                if c.pos.is_some() { "no coordinates for this system".into() } else { "waiting for the carrier's position".into() }));
            return rows;
        };
        let to_target = c.pos.map(|p| crate::route::dist(&p, &hop.target_pos));
        rows.push(row("Destination", target.to_string(), String::new(), to_target, "from the Map tab".into()));
        match hop.next {
            Some((next, jump, left)) => {
                let fuel = c.used_t.zip(c.fuel).map(|(u, f)| journal::carrier_tritium(jump, u, f));
                let more = (left / database::CARRIER_RANGE_LY).ceil() as i64;
                let note = format!(
                    "{}{}",
                    fuel.map_or("Tritium unknown".to_string(), |t| format!("about {t} t Tritium")),
                    if left < 1.0 { "  \u{00B7}  arrives".to_string() } else { format!("  \u{00B7}  {} ly left, at least {more} more jump(s)", light_years(left)) }
                );
                rows.push(row("Next jump", next, String::new(), Some(jump), note));
            }
            None => rows.push(row("Next jump", String::new(), String::new(), None,
                format!("no known system within {} ly gets closer", light_years(database::CARRIER_RANGE_LY)))),
        }
        rows
    }

    fn show_engineers(&self) {
        if let Some(pos) = self.pos {
            main_window::show_engineers(crate::engineers::nearest(pos));
            main_window::show_guardian(crate::alien::nearest(pos, crate::alien::GUARDIAN));
            main_window::show_thargoid(crate::alien::nearest(pos, crate::alien::THARGOID));
        }
    }

    pub fn refresh(&mut self, moved: bool) {
        let sector = self.sector.clone();
        let asks = self.read_asks(moved);
        self.ask(asks, Then::Paint { sector }, false, Some("refresh"));
    }

    fn paint_from(&mut self, mut r: Results, sector: Option<String>) {
        if sector != self.sector {
            return;
        }
        if let Some(rows) = take_rows(&mut r, "carrier_targets") {
            self.carrier_rows = Some(rows);
            self.solve_chains();
        }
        if let Some(rows) = take_rows(&mut r, "neutron_targets") {
            self.neutron_rows = Some(rows);
        }
        let mut nearest = self.carrier_rows.clone().unwrap_or_default();
        match &self.route {
            Some(route) => nearest.extend(route.iter().take(NEUTRON_ROWS).cloned()),
            None => nearest.extend(self.neutron_rows.clone().unwrap_or_default()),
        }
        nearest.extend(self.route_rows());
        let nearest = self.dress_nearest(nearest);
        let confirmed = take_rows(&mut r, "confirmed_targets").unwrap_or_default();
        let adjacent = take_rows(&mut r, "adjacent_sectors").unwrap_or_default();
        let targets = take_rows(&mut r, "top_targets").unwrap_or_default();
        let unfound = take_rows(&mut r, "unfound_targets").unwrap_or_default();
        let totals = take_rows(&mut r, "sector_totals").unwrap_or_default();
        let region = take_rows(&mut r, "region_totals").unwrap_or_default();
        let summary = match r.remove("sector_summary") {
            Some(Answer::Summary(s)) => s,
            _ => [0; 4],
        };
        let _p = self.timing.phase("paint");
        self.paint(confirmed, nearest, adjacent, targets, unfound, totals, region, summary);
    }

    #[allow(clippy::too_many_arguments)]
    fn paint(
        &mut self,
        confirmed: Vec<Row>,
        nearest: Vec<Row>,
        adjacent: Vec<Row>,
        targets: Vec<Row>,
        unfound: Vec<Row>,
        totals: Vec<Row>,
        region: Vec<Row>,
        summary: [i64; 4],
    ) {
        {
            let _p = self.timing.phase("p_nearest");
            self.tables[NEAR].show(nearest.clone());
        }
        {
            let _p = self.timing.phase("p_confirmed");
            self.tables[CONF].show(confirmed.clone());
        }
        if trace::enabled() {
            crate::trace!("adjacent", n = adjacent.len());
            for (i, a) in adjacent.iter().enumerate() {
                crate::trace!(
                    format!("adjacent[{i}]"),
                    system = a.system.clone(),
                    type_label = a.type_label.clone(),
                    copy_text = a.copy_text.clone(),
                    p_bh = a.p[0]
                );
            }
        }
        self.rows[CONF] = confirmed.clone();
        self.rows[NEAR] = nearest;

        if self.sector.is_none() {
            self.rows[SECT] = Vec::new();
            {
                let _p = self.timing.phase("p_cursor");
                self.place_cursor(false);
            }
            self.tables[SECT].blank();
            self.note("waiting for a position from the journal", Role::Warn);
            self.redraw();
            return;
        }
        {
            let _p = self.timing.phase("p_sector");
            let here = totals.into_iter().map(|t| Row { cube: Some([0; 3]), ..t });
            let rows: Vec<Row> = targets.iter().chain(unfound.iter()).cloned().chain(here).chain(adjacent).collect();
            let mut shown = rows.clone();
            shown.extend(region.into_iter().filter(|r| r.grp() == ROW_REGION));
            self.tables[SECT].show(shown);
            self.rows[SECT] = rows;
        }
        {
            let _p = self.timing.phase("p_cursor");
            self.place_cursor(false);
        }
        let [total, visited, settled, catalogued] = summary;
        let sector = self.sector.clone().unwrap_or_default();
        if self.crafted {
            let system = self.system.clone().unwrap_or_default();
            self.note(
                &format!(
                    "{system} is hand-named -- no procedural sector. Showing the 'crafted' sentinel, which \
                     collects EVERY hand-named system in the galaxy, so these totals and distances are \
                     galaxy-wide."
                ),
                Role::Warn,
            );
        } else if targets.is_empty() {
            let mut why = if total == 0 {
                let extra = if catalogued != 0 {
                    format!(" ({} plot only, excluded)", thousands_i(catalogued))
                } else {
                    String::new()
                };
                format!("no boxel-predicted systems in {sector}{extra}")
            } else {
                let parts: Vec<String> = [
                    (visited != 0).then(|| format!("{} visited", thousands_i(visited))),
                    (settled != 0).then(|| format!("{} already classed", thousands_i(settled))),
                ]
                .into_iter()
                .flatten()
                .collect();
                if parts.is_empty() {
                    format!(
                        "the {} predicted system(s) in {sector} are all confirmed or marked wrong",
                        thousands_i(total)
                    )
                } else {
                    format!("all {} predicted system(s) in {sector} settled -- {}", thousands_i(total), parts.join(" and "))
                }
            };
            if !unfound.is_empty() {
                why += &format!(
                    " -- but {} catalogued star(s) should be here and cannot be found by name",
                    unfound.len()
                );
            }
            self.note(&why, Role::Warn);
        } else {
            let spread: HashSet<(Option<u64>, Option<u64>)> =
                targets.iter().map(|t| (t.p[0].map(f64::to_bits), t.p[1].map(f64::to_bits))).collect();
            self.note(
                &format!(
                    "{sector}: {} boxel-predicted, {} visited, {} already classed, {} plot only  |  {} distinct \
                     BH/WR rate(s) in the top {}  |  nearest confirmed: {}",
                    thousands_i(total),
                    thousands_i(visited),
                    thousands_i(settled),
                    thousands_i(catalogued),
                    spread.len(),
                    targets.len(),
                    Self::nearest_confirmed(&confirmed)
                ),
                Role::Dim,
            );
        }
        self.redraw();
    }

    fn recount(&mut self) {
        if self.ui.chrome {
            self.ask(vec![Ask::Counts], Then::Counted, false, Some("counts"));
        }
    }

    fn update_status(&mut self) {
        if !self.ui.chrome {
            return;
        }
        let c = |k: &str| thousands_i(self.counts.get(k).copied().unwrap_or(0));
        let text = format!(
            "{}   seen {} / visited {} / found {}   {}",
            self.system.clone().unwrap_or_else(|| "waiting for a jump".into()),
            c("system_seen"),
            c("system_visited"),
            c("system_confirmed"),
            local_hh_mm()
        );
        self.ui.set_status(text);
        self.redraw();
    }

    fn targeted_class(&self, status: &Value) -> Option<String> {
        let (name, star_class) = self.next_jump.as_ref()?;
        let dest = status.get("Destination").and_then(|d| d.get("Name")).and_then(Value::as_str);
        if dest != Some(name.as_str()) || Some(name) == self.system.as_ref() {
            return None;
        }
        star_class.clone()
    }

    fn filled(&self) -> Vec<usize> {
        (0..3).filter(|&i| self.rows[i].iter().any(Row::selectable)).collect()
    }

    fn place_cursor(&mut self, copy: bool) {
        let live = self.filled();
        if live.is_empty() {
            for t in &mut self.tables {
                t.set_selected(None);
            }
            return;
        }
        if !live.contains(&self.active) {
            self.active = live[0];
        }
        let rows = &self.rows[self.active];
        if !copy
            && let Some(copied) = &self.copied
                && let Some(at) = rows.iter().position(|r| r.target() == Some(copied.as_str())) {
                    self.cursor = at;
                }
        self.cursor = self.cursor.min(rows.len().saturating_sub(1));
        if let Some(at) = Self::selectable_from(rows, self.cursor, 1) {
            self.cursor = at;
        }
        for (i, t) in self.tables.iter_mut().enumerate() {
            t.set_selected((i == self.active).then_some(self.cursor));
        }
        let now = self.rows[self.active].get(self.cursor).and_then(|r| r.target()).map(String::from);
        if copy || (self.copied.is_some() && now != self.copied) {
            self.copy_selected();
        }
        self.flash_copied();
    }

    fn remember(&mut self) {
        if let Some(t) = self.rows[self.active].get(self.cursor).and_then(|r| r.target()) {
            self.marks.insert(self.active, t.to_string());
        }
    }

    fn recall(&self, index: usize) -> usize {
        let Some(mark) = self.marks.get(&index) else { return 0 };
        self.rows[index].iter().position(|r| r.target() == Some(mark.as_str())).unwrap_or(0)
    }

    fn move_cursor(&mut self, action: Action) {
        let live = self.filled();
        if live.is_empty() {
            self.note("nothing to select yet", Role::Warn);
            return;
        }
        match action {
            Action::NextTable | Action::PrevTable => {
                let step: isize = if action == Action::NextTable { 1 } else { -1 };
                let nxt = match live.iter().position(|&i| i == self.active) {
                    Some(at) => live[(at as isize + step).rem_euclid(live.len() as isize) as usize],
                    None => live[0],
                };
                self.remember();
                self.active = nxt;
                self.cursor = self.recall(nxt);
            }
            _ => {
                let rows = &self.rows[self.active];
                let n = rows.len().max(1) as isize;
                let step: isize = if action == Action::NextRow { 1 } else { -1 };
                let from = (self.cursor as isize + step).rem_euclid(n) as usize;
                self.cursor = Self::selectable_from(rows, from, step).unwrap_or(from);
            }
        }
        self.place_cursor(true);
        self.redraw();
    }

    fn selectable_from(rows: &[Row], from: usize, step: isize) -> Option<usize> {
        let n = rows.len() as isize;
        (0..n).map(|k| (from as isize + k * step).rem_euclid(n) as usize).find(|&i| rows[i].selectable())
    }

    fn mark_wrong(&mut self) {
        let name = Self::table_name(self.active);
        let Some(row) = self.rows[self.active].get(self.cursor).cloned() else {
            self.note("nothing selected to mark", Role::Warn);
            return;
        };
        let Some(source) = wrong_source(row.grp()).filter(|_| row.names_a_system()) else {
            self.note(
                &format!("{name} {} is not a prediction -- SHIFT+BACKSPACE only retires a guess", self.cursor + 1),
                Role::Warn,
            );
            return;
        };
        let system = row.target().unwrap_or_default().to_string();
        let offered_under = if row.grp() == ROW_SECTOR { row.system.clone() } else { self.sector.clone() };
        self.advance_clipboard(&HashSet::from([system.clone()]), &RETIRED_BY_WRONG);
        let sector = self.sector.clone();
        let mut asks = vec![Ask::MarkWrong { system: system.clone(), source: source.into(), sector: offered_under }];
        asks.extend(self.read_asks(false));
        self.ask(asks, Then::Marked { system, sector }, true, None);
    }

    fn copy_selected(&mut self) {
        let name = Self::table_name(self.active);
        let Some(row) = self.rows[self.active].get(self.cursor).cloned() else { return };
        let text = row.target().unwrap_or_default().to_string();
        let shown = row.system.clone().unwrap_or_default();
        let what = if text == shown { text.clone() } else { format!("{text}  (best in {shown})") };
        let ok = {
            let _p = self.timing.phase("p_clipboard");
            clipboard::copy(&text)
        };
        crate::trace!("copy", table = name, at = self.cursor, shown = shown.clone(), copied = text.clone(), ok = ok);
        if !ok {
            self.note(&format!("could not reach the clipboard ({what})"), Role::Warn);
            return;
        }
        self.took_clipboard(&text);
        if row.grp() == ROW_ROUTE {
            self.follow_route(&row);
        } else {
            if let Some(f) = self.follow.take() {
                let dest = self.chain_dest(&f.label);
                self.note(&format!("stopped following {dest}"), Role::Dim);
            }
            self.note(&format!("{name} {}: copied {what}", self.cursor + 1), Role::Ok);
        }
    }

    fn advance_clipboard(&mut self, gone: &HashSet<String>, removable: &[i64]) -> bool {
        if self.copied.is_none() || gone.is_empty() {
            return false;
        }
        if !self.filled().contains(&self.active) {
            return false;
        }
        let name = Self::table_name(self.active);
        let rows = &self.rows[self.active];
        let Some(row) = rows.get(self.cursor) else { return false };
        let offers = row.target().unwrap_or_default().to_string();
        let answered = gone.contains(&offers);
        crate::trace!(
            "advance",
            offers = offers.clone(),
            answered = answered,
            grp = row.row_grp,
            removable = removable.contains(&row.grp()),
            cached = row.candidates.len()
        );
        if !answered || !removable.contains(&row.grp()) {
            return false;
        }
        let nxt = self.successor(gone, removable);
        crate::trace!("advance-to", next = nxt.clone(), clipboard = self.copied.clone());
        let Some(nxt) = nxt.filter(|n| Some(n) != self.copied.as_ref()) else { return false };
        if !clipboard::copy(&nxt) {
            return false;
        }
        self.took_clipboard(&nxt);
        self.note(&format!("{name} {}: answered -- copied {nxt}", self.cursor + 1), Role::Ok);
        true
    }

    fn assert_alias(&mut self) {
        let key = hotkeys::key_label(&hotkeys::binding(Action::AliasRouted));
        let Some(dest) = &self.plotted else {
            self.note(
                &format!("no route plotted -- {key} states that the selected row IS the destination of the route now up"),
                Role::Warn,
            );
            return;
        };
        let name = Self::table_name(self.active);
        let Some(row) = self.rows[self.active].get(self.cursor).cloned() else {
            self.note("nothing selected to alias", Role::Warn);
            return;
        };
        if !ALIAS_SOURCE.contains(&row.grp()) || !row.names_a_system() {
            self.note(
                &format!("{name} {} is not a guess -- {key} only renames a prediction or an unfound star", self.cursor + 1),
                Role::Warn,
            );
            return;
        }
        let system = row.target().unwrap_or_default().to_string();
        let canonical = dest.name.clone();
        let (id64, xyz, star_class) = (dest.id64, dest.xyz, dest.star_class.clone());
        if system == canonical {
            self.note(&format!("{system} is already the route's destination -- nothing to alias"), Role::Warn);
            return;
        }
        if row.grp() != ROW_UNFOUND && names::boxel_index(&system) != names::boxel_index(&canonical) {
            self.note(&format!("index differs ({system} vs {canonical}) -- recording anyway"), Role::Warn);
        }
        crate::trace!("alias", system = system.clone(), canonical = canonical.clone(), id64 = id64);
        let sector = self.sector.clone();
        let mut asks = vec![Ask::RecordAlias {
            system: system.clone(),
            canonical: canonical.clone(),
            id64,
            xyz,
            star_class,
            ts: crate::log::utc_iso_seconds(),
        }];
        asks.extend(self.read_asks(false));
        self.ask(asks, Then::Aliased { system, canonical, sector }, true, None);
    }

    fn trace_cursor(&self, tag: &str, revealed: usize) {
        if !trace::enabled() {
            return;
        }
        let row = self.rows[self.active].get(self.cursor);
        crate::trace!(
            tag,
            table = Self::table_name(self.active),
            at = self.cursor,
            of = self.rows[self.active].len(),
            shown = row.and_then(|r| r.system.clone()),
            offers = row.and_then(|r| r.target().map(String::from)),
            grp = row.and_then(|r| r.row_grp),
            clipboard = self.copied.clone(),
            revealed = revealed
        );
    }

    fn took_clipboard(&mut self, text: &str) {
        self.copied = Some(text.to_string());
        self.pending_flash = Some(text.to_string());
        notify::copied(!self.args.no_sound);
    }

    fn flash_copied(&mut self) {
        let Some(text) = self.pending_flash.take() else { return };
        for t in &mut self.tables {
            t.flash(std::slice::from_ref(&text), FLASH_COPIED);
        }
    }

    fn successor(&self, gone: &HashSet<String>, removable: &[i64]) -> Option<String> {
        let rows = &self.rows[self.active];
        let cached = &rows[self.cursor].candidates;
        if !cached.is_empty() {
            return cached.iter().find(|c| !gone.contains(*c)).cloned();
        }
        for r in rows[self.cursor + 1..].iter().filter(|r| r.selectable()) {
            let t = r.target().unwrap_or_default();
            if gone.contains(t) && removable.contains(&r.grp()) {
                continue;
            }
            return Some(t.to_string());
        }
        None
    }

    fn dest_of(hops: &[Hop]) -> Option<PlottedDest> {
        let last = hops.last()?;
        Some(PlottedDest {
            name: last.system.clone(),
            id64: last.id64,
            xyz: [last.x, last.y, last.z],
            star_class: last.star_class.clone(),
        })
    }

    fn poll_navroute(&mut self) {
        if let Gated::Changed(hops) = journal::read_navroute(&self.args.journal_dir, &mut self.navroute_mtime) {
            self.plotted = Self::dest_of(&hops);
            self.route_hops = hops.clone();
            if !hops.is_empty() {
                let note = format!("route plotted: {} hop(s)", hops.len());
                self.record_revealed(hops, Some(note));
            }
        }
    }

    fn chime_worthy(finds: &[(String, String)], fresh: &HashSet<String>, boxel: &HashSet<String>) -> bool {
        let candidates: Vec<&(String, String)> = finds.iter().filter(|(n, _)| fresh.contains(n)).collect();
        if candidates.iter().any(|(_, c)| kinds::is_chime_class(c)) {
            return true;
        }
        candidates.iter().any(|(n, c)| kinds::is_chime_if_predicted(c) && boxel.contains(n))
    }

    fn record_revealed(&mut self, rows: Vec<Hop>, note: Option<String>) {
        if rows.is_empty() {
            return;
        }
        self.trace_cursor("reveal-in", rows.len());
        let answered: HashSet<String> =
            rows.iter().filter(|h| h.star_class.is_some()).map(|h| h.system.clone()).collect();
        self.advance_clipboard(&answered, &SETTLED_BY_CLASS);
        let stamp = crate::log::utc_iso_seconds();
        let finds: Vec<(String, String)> = rows
            .iter()
            .filter_map(|h| {
                let c = kinds::arrival_class(h.star_class.as_deref()?, &h.system);
                kinds::is_rare_class(c).then(|| (h.system.clone(), c.to_string()))
            })
            .collect();
        let maybe: Vec<String> =
            finds.iter().filter(|(_, c)| kinds::is_chime_if_predicted(c)).map(|(n, _)| n.clone()).collect();
        let names: Vec<String> = rows.iter().map(|h| h.system.clone()).filter(|n| !n.is_empty()).collect();
        let mut asks = vec![
            Ask::RecordSeen { rows, ts: Some(stamp) },
            Ask::PromoteConfirmed { only: Only::FromRecordSeen },
        ];
        if !maybe.is_empty() {
            asks.push(Ask::PredictedBoxel { names: maybe });
        }
        if trace::enabled() {
            asks.push(Ask::SettledBy { names });
        }
        asks.extend(self.read_asks(false));
        let sector = self.sector.clone();
        self.ask(asks, Then::Revealed { finds, note, sector }, true, None);
    }

    fn revealed(&mut self, mut r: Results, finds: Vec<(String, String)>, note: Option<String>, sector: Option<String>) {
        let new: HashSet<String> = match r.remove("record_seen") {
            Some(Answer::Names(n)) => n.into_iter().collect(),
            _ => HashSet::new(),
        };
        let promoted = match r.remove("promote_confirmed") {
            Some(Answer::Count(n)) => n,
            _ => 0,
        };
        let settled = match r.remove("settled_by") {
            Some(Answer::Settled(s)) => s,
            _ => Vec::new(),
        };
        crate::trace!(
            "reveal-out",
            new = new.len(),
            promoted = promoted,
            rare = finds.len(),
            settled = settled.len(),
            boxel = settled.iter().filter(|s| !s.is_catalog).count(),
            catalogued = settled.iter().filter(|s| s.is_catalog).count()
        );
        if trace::enabled() {
            crate::trace!("settled", n = settled.len());
            for (i, s) in settled.iter().enumerate() {
                crate::trace!(
                    format!("settled[{i}]"),
                    system = s.system.clone(),
                    sector = s.sector.clone(),
                    is_catalog = s.is_catalog,
                    was_classed = s.was_classed.clone()
                );
            }
        }
        let boxel = match r.remove("predicted_boxel") {
            Some(Answer::NameSet(s)) => s,
            _ => HashSet::new(),
        };
        let worth_hearing = Self::chime_worthy(&finds, &new, &boxel);
        self.recount();
        self.paint_from(r, sector);
        if !finds.is_empty() {
            let what: Vec<String> = finds.iter().take(3).map(|(n, c)| format!("{n} [{c}]")).collect();
            let more = if finds.len() > 3 { format!(" (+{})", finds.len() - 3) } else { String::new() };
            self.note(&format!("CONFIRMED {} rare -- {}{more}", finds.len(), what.join(", ")), Role::Ok);
            let names: Vec<String> = finds.iter().map(|(n, _)| n.clone()).collect();
            self.tables[CONF].flash(&names, FLASH_CONFIRM);
            self.redraw();
            if worth_hearing {
                notify::chime(!self.args.no_sound);
            }
        } else if let Some(note) = note {
            self.note(&format!("{note}, {} new", new.len()), Role::Dim);
        }
    }

    fn toggle_neutron_route(&mut self) {
        if self.route.is_some() {
            self.clear_neutron_route("neutron jump mode OFF");
            return;
        }
        let Some(row) = self.rows[self.active].get(self.cursor).cloned() else {
            self.note("nothing selected to route to", Role::Warn);
            return;
        };
        let dest = row.target().unwrap_or_default().to_string();
        let Some(xyz) = row.xyz() else {
            self.note(
                &format!(
                    "no coordinates for {dest} -- SHIFT+N routes from the sector, confirmed, unfound and neutron \
                     tables"
                ),
                Role::Warn,
            );
            return;
        };
        if self.pos.is_none() {
            self.note("no position yet -- cannot plot a route from nowhere", Role::Warn);
            return;
        }
        self.plot_neutron_route(dest, xyz);
    }

    fn plot_neutron_route(&mut self, dest: String, dest_xyz: [f64; 3]) {
        if self.jump_range.is_none() {
            self.note("no jump range -- cannot plot without knowing how far you jump", Role::Warn);
            return;
        }
        let direct = dist(&self.pos.unwrap(), &dest_xyz);
        if direct > route::MAX_ROUTE_LY {
            self.note(
                &format!(
                    "{dest} is {} ly away -- neutron routing is capped at {} ly",
                    light_years(direct),
                    light_years(route::MAX_ROUTE_LY)
                ),
                Role::Warn,
            );
            return;
        }
        self.route_attempt(dest, dest_xyz, vec![600.0, 2500.0]);
    }

    fn route_attempt(&mut self, dest: String, dest_xyz: [f64; 3], pads: Vec<f64>) {
        let Some(pos) = self.pos else { return };
        let pad = pads[0];
        let rest = pads[1..].to_vec();
        self.ask(
            vec![Ask::NeutronCorridor { start: pos, dest: dest_xyz, pad }],
            Then::Routed { dest, dest_xyz, rest },
            false,
            Some("route"),
        );
    }

    fn routed(&mut self, mut r: Results, dest: String, dest_xyz: [f64; 3], rest: Vec<f64>) {
        let (Some(pos), Some(jump)) = (self.pos, self.jump_range) else { return };
        let boosted = jump * ship::neutron_boost(self.loadout.as_ref());
        let direct = dist(&pos, &dest_xyz);
        let Some(Answer::Points(names, xyz)) = r.remove("neutron_corridor") else { return };
        let hops = {
            let _p = self.timing.phase("route_search");
            route::plan(&xyz, &pos, &dest_xyz, jump, boosted)
        };
        let Some(hops) = hops else {
            if !rest.is_empty() {
                self.route_attempt(dest, dest_xyz, rest);
                return;
            }
            self.note(
                &format!(
                    "no neutron route to {dest} ({} ly) at {} ly ({} ly boosted) -- nothing \
                     reachable in the corridor",
                    light_years(direct),
                    light_years(jump),
                    light_years(boosted)
                ),
                Role::Warn,
            );
            return;
        };
        let mut route: Vec<Row> = hops.iter().map(|&i| self.route_row(&names[i], xyz[i], false)).collect();
        route.push(self.route_row(&dest, dest_xyz, true));
        let n = route.len();
        self.route = Some(route);
        self.route_dest = Some(dest.clone());
        self.copy_next_hop(&format!("neutron route to {dest}: {n} jump(s)"));
        self.refresh(false);
    }

    fn clear_neutron_route(&mut self, why: &str) {
        self.route = None;
        self.route_dest = None;
        self.note(why, Role::Dim);
        self.refresh(false);
    }

    fn route_row(&self, name: &str, xyz: [f64; 3], last: bool) -> Row {
        Row {
            rank: Some(0),
            system: Some(name.to_string()),
            type_label: Some(if last { "ARRIVE" } else { "BOOST" }.into()),
            dist_ly: self.pos.map(|p| dist(&p, &xyz)),
            row_grp: Some(ROW_NEUTRON),
            wide_text: Some(if last { "DESTINATION" } else { "-" }.into()),
            x: Some(xyz[0]),
            y: Some(xyz[1]),
            z: Some(xyz[2]),
            ..Row::default()
        }
    }

    fn copy_next_hop(&mut self, prefix: &str) {
        let Some(nxt) = self.route.as_ref().and_then(|r| r.first()).and_then(|r| r.system.clone()) else { return };
        if clipboard::copy(&nxt) {
            self.took_clipboard(&nxt);
            self.note(&format!("{prefix} -- copied {nxt}"), Role::Ok);
        } else {
            self.note(&format!("{prefix} -- could not reach the clipboard ({nxt})"), Role::Warn);
        }
    }

    fn advance_route(&mut self, system: &str) -> bool {
        let Some(route) = &self.route else { return false };
        let Some(at) = route.iter().position(|r| r.system.as_deref() == Some(system)) else { return false };
        let last = at == route.len() - 1;
        let remaining: Vec<Row> = route[at + 1..].to_vec();
        let dest = self.route_dest.clone().unwrap_or_default();
        if last || remaining.is_empty() {
            self.clear_neutron_route(&format!("neutron route complete: arrived at {dest}"));
            return true;
        }
        let n = remaining.len();
        self.route = Some(remaining);
        let skipped = if at > 0 { format!(", {at} skipped") } else { String::new() };
        self.copy_next_hop(&format!("{n} jump(s) left to {dest}{skipped}"));
        true
    }

    fn check_focus(&mut self) {
        let shown = self.args.always_visible || focus::is_foreground();
        let gui = self.status.as_ref().and_then(|s| s.get("GuiFocus")).and_then(Value::as_u64).unwrap_or(0);
        self.ui.set_visible(shown && !GUI_HIDES_LEFT.contains(&gui));
        self.top.set_visible(shown && !GUI_HIDES_TOP.contains(&gui));
        self.right.set_visible(shown && !GUI_HIDES_RIGHT.contains(&gui));
    }

    pub fn tick(&mut self) {
        let timing = self.timing.clone();
        let _span = timing.span("tick");
        self.tick_inner();
    }

    fn tick_inner(&mut self) {
        self.drain_db();
        if let Some(quotes) = self.market.drain() {
            main_window::show_tritium(quotes);
        }
        if let Some(rebound) = hotkeys::take_rebound() {
            self.rebound(rebound);
        }
        for ask in main_window::take_asks() {
            match ask {
                UiAsk::Regions => {
                    self.ask(vec![Ask::RegionExpected { catalogued: true }], Then::Regions, false, Some("regions"))
                }
                UiAsk::MapRegions { catalogued } => self.ask(
                    vec![Ask::RegionExpected { catalogued }],
                    Then::MapRegions,
                    false,
                    Some("map_regions"),
                ),
                UiAsk::MapGrid => self.ask(vec![Ask::MapGrid], Then::MapGrid, false, Some("map_grid")),
                UiAsk::Trade => self.ask_trade(),
                UiAsk::Engineers | UiAsk::Alien => self.show_engineers(),
                UiAsk::Carrier => self.refresh_carrier(),
                UiAsk::CarrierRoute { destination } => match destination.map(String::from).or_else(|| self.last_pick.clone()) {
                    Some(target) => {
                        say!("carrier destination set to {target}: the Carrier tab has the next jump");
                        let callsign = self.carrier.as_ref().and_then(|c| c.callsign.clone()).unwrap_or_default();
                        self.ask(
                            vec![Ask::SetCarrierDestination { callsign, destination: target.clone() }],
                            Then::Counted,
                            true,
                            None,
                        );
                        self.carrier_target = Some(target);
                        self.refresh_carrier();
                    }
                    None => say!("click a sector on the Map tab first: its likeliest target becomes the carrier's destination"),
                },
                UiAsk::Outcomes => self.ask(vec![Ask::Outcomes], Then::Outcomes, false, Some("outcomes")),
                UiAsk::SectorBest { sector, catalogued, column, kind } => self.ask(
                    vec![Ask::SectorBest { sector: sector.clone(), catalogued, column }],
                    Then::Picked { sector, kind },
                    false,
                    Some("sector_best"),
                ),
                UiAsk::Sectors { region_id, catalogued, column, limit } => self.ask(
                    vec![Ask::SectorExpected { region_id, catalogued, column, limit }],
                    Then::Sectors,
                    false,
                    Some("sectors"),
                ),
            }
        }
        {
            let _p = self.timing.phase("focus");
            self.check_focus();
        }
        {
            let _p = self.timing.phase("clock");
            self.update_clock();
        }
        if hotkeys::take_wrong() && focus::is_foreground() {
            let _p = self.timing.phase("key_wrong");
            self.mark_wrong();
        }
        if hotkeys::take_route() && focus::is_foreground() {
            let _p = self.timing.phase("key_route");
            self.toggle_neutron_route();
        }
        if hotkeys::take_alias() && focus::is_foreground() {
            let _p = self.timing.phase("key_alias");
            self.assert_alias();
        }
        if let Some(pressed) = hotkeys::take()
            && focus::is_foreground() {
                let _p = self.timing.phase("key");
                self.move_cursor(pressed);
            }
        if self.args.sector.is_some() {
            return;
        }
        let mut rows = Vec::new();
        let mut note = None;
        {
            let _p = self.timing.phase("navroute");
            if let Gated::Changed(hops) = journal::read_navroute(&self.args.journal_dir, &mut self.navroute_mtime) {
                self.plotted = Self::dest_of(&hops);
                self.route_hops = hops.clone();
                crate::trace!(
                    "navroute",
                    hops = hops.len(),
                    first = hops.first().map(|h| h.system.clone()),
                    dest = hops.last().map(|h| h.system.clone()),
                    dest_class = hops.last().and_then(|h| h.star_class.clone()),
                    no_class = hops.iter().filter(|h| h.star_class.is_none()).count()
                );
                if !hops.is_empty() {
                    note = Some(format!("route plotted: {} hop(s)", hops.len()));
                }
                rows = hops;
            }
        }
        let mut events = Vec::new();
        let due = self.last_poll.is_none_or(|t| t.elapsed().as_secs_f64() >= self.args.poll);
        if due {
            self.last_poll = Some(Instant::now());
            {
                let _p = self.timing.phase("journal");
                events = self.reader.poll();
            }
            let targets: Vec<journal::ClassRow> = events
                .iter()
                .filter(|e| journal::CLASS_EVENTS.contains(&journal::event_name(e)))
                .map(journal::class_of)
                .collect();
            for t in &targets {
                if let (Some(n), Some(c)) = (&t.system, &t.star_class) {
                    rows.push(Hop { system: n.clone(), star_class: Some(c.clone()), x: None, y: None, z: None, id64: t.id64 });
                }
            }
            if let Some(last) = targets.last()
                && let Some(n) = &last.system {
                    self.next_jump = Some((n.clone(), last.star_class.clone()));
                    self.next_jump_id64 = last.id64;
                }
        }
        self.record_revealed(rows, note);
        if events.iter().fold(false, |changed, e| self.here.fold(e) | changed) {
            self.seed_here();
            self.ask_exobio_here();
        }
        let mut outcome_asks = Vec::new();
        for e in &events {
            let name = journal::event_name(e);
            if journal::SHIP_EVENTS.contains(&name) {
                self.take_loadout(Some(e.clone()));
            }
            if journal::POS_EVENTS.contains(&name) {
                self.on_position(e, true);
            }
            if name == "Scan"
                && let Some(scan) = journal::star_scan(e) {
                    outcome_asks.push(Ask::OutcomeScan { system: scan.system, body: scan.body, star_type: scan.star_type });
                }
            if name == "FSSAllBodiesFound"
                && let Some(system) = journal::all_bodies_found(e) {
                    outcome_asks.push(Ask::OutcomeComplete { system });
                }
        }
        if !outcome_asks.is_empty() {
            outcome_asks.push(Ask::Outcomes);
            self.ask(outcome_asks, Then::Outcomes, true, None);
        }
        if events.iter().any(|e| journal::CARRIER_EVENTS.contains(&journal::event_name(e))) {
            self.refresh_carrier();
        }
        {
            let _p = self.timing.phase("lights");
            if let Gated::Changed(status) = journal::read_status(&self.args.journal_dir, &mut self.status_mtime) {
                self.status = Some(status);
            }
            if let Some(status) = self.status.clone() {
                self.lights.fuel(lights::fuel_fraction(Some(&status), self.loadout.as_ref()));
                let class = self.targeted_class(&status);
                self.lights.target(class.as_deref());
                self.lights.ship(Some(&status), self.loadout.as_ref());
            }
        }
        if !events.is_empty() {
            let _p = self.timing.phase("status");
            self.update_status();
        }
        self.update_jump();
    }

    fn charging(&self) -> bool {
        self.status.as_ref().and_then(|s| s.get("Flags")).and_then(Value::as_u64).is_some_and(|f| f & FSD_CHARGING != 0)
    }

    fn update_jump(&mut self) {
        for (name, got) in self.lookup.take() {
            match got {
                Ok(info) => {
                    self.infos.insert(name, Some(info));
                }
                Err(e) => say!("lookup {name}: {e}"),
            }
        }
        if self.seed_here() {
            self.ask_exobio_here();
        }
        let panel = self.next_jump.clone().and_then(|(target, class)| {
            let ahead = self.route_hops.iter().skip(1).any(|h| h.system == target);
            if self.system.as_deref() == Some(target.as_str()) || !(ahead || self.charging()) {
                return None;
            }
            if !self.infos.contains_key(&target) {
                let id64 = self.route_hops.iter().find(|h| h.system == target).and_then(|h| h.id64).or(self.next_jump_id64);
                self.infos.insert(target.clone(), None);
                self.lookup.ask(&target, id64);
            }
            let mut p = jump::build(&self.route_hops, &target, class.as_deref(), self.jump_range);
            let info = self.infos.get(&target).and_then(Option::as_ref);
            p.star = jump::star_text(p.class.as_deref(), info);
            p.counts = jump::counts_text(info);
            p.carrier = jump::carrier(info);
            p.discovery = jump::discovery_line(info, p.class.as_deref().map(|c| kinds::arrival_class(c, &target)));
            p.bio = self.exo_target_line(&target);
            Some(p)
        });
        let target = panel.as_ref().map(|p| p.target.clone());
        if target.is_some() && target != self.exo_target_for {
            self.exo_target_for = target.clone();
            let id64 = self.route_hops.iter().find(|h| Some(&h.system) == target.as_ref()).and_then(|h| h.id64).or(self.next_jump_id64);
            let system = target.unwrap_or_default();
            self.ask(vec![Ask::ExobioTarget { system, id64 }], Then::Exobio, false, Some("exobio_target"));
        }
        if panel != self.jump {
            self.jump = panel;
            self.redraw();
        }
    }

    fn exo_target_line(&self, target: &str) -> Option<(String, Role)> {
        self.exo_target.as_ref().filter(|t| t.system == target).map(exobio::target_line)
    }

    fn seed_here(&mut self) -> bool {
        let Some(system) = self.here.system.clone() else { return false };
        match self.infos.get(&system) {
            Some(Some(info)) => {
                let exo = info.exo.clone();
                self.here.seed(&exo)
            }
            Some(None) => false,
            None => {
                self.infos.insert(system.clone(), None);
                self.lookup.ask(&system, self.here.address);
                false
            }
        }
    }

    fn ask_exobio_here(&mut self) {
        let asks = vec![Ask::ExobioHere { bodies: self.here.json(), star: self.here.star.clone() }];
        self.ask(asks, Then::Exobio, false, Some("exobio_here"));
    }

    fn ask_exobio_nearby(&mut self) {
        if let Some(pos) = self.pos {
            self.ask(vec![Ask::ExobioNearby { pos, limit: exobio::NEARBY_ROWS }], Then::Exobio, false, Some("exobio_nearby"));
        }
    }

    fn took_exobio(&mut self, mut r: Results) {
        if let Some(Answer::ExoBodies(rows)) = r.remove("exobio_here") {
            self.exo_here = rows;
        }
        if let Some(Answer::ExoSystem(row)) = r.remove("exobio_target") {
            self.exo_target = row;
            if let Some(target) = self.jump.as_ref().map(|j| j.target.clone()) {
                let bio = self.exo_target_line(&target);
                if let Some(j) = self.jump.as_mut() {
                    j.bio = bio;
                }
            }
        }
        if let Some(Answer::ExoSystems(rows)) = r.remove("exobio_nearby") {
            self.exo_near = rows;
        }
        self.rebuild_exobio();
        self.redraw();
    }

    fn rebuild_exobio(&mut self) {
        self.exo_sheets = [
            exobio::here_sheet(self.here.system.as_deref(), &self.exo_here),
            exobio::nearby_sheet(&self.exo_near, database::EXOBIO_RANGE_LY),
        ]
        .into_iter()
        .flatten()
        .collect();
    }

    pub fn run_startup(&mut self) {
        self.ask(vec![Ask::CarrierDestination], Then::CarrierDestination, false, Some("carrier_destination"));
        if let Some(sector) = self.args.sector.clone() {
            self.sector = Some(sector.clone());
            self.system = Some(format!("(forced: {sector})"));
            self.refresh(true);
            self.update_status();
        } else {
            for e in self.reader.harvest() {
                self.here.fold(&e);
            }
            self.seed_here();
            self.ask_exobio_here();
            let harvested = self.reader.harvest_classes();
            if let Some(last) = harvested.last()
                && let Some(n) = &last.system {
                    self.next_jump = Some((n.clone(), last.star_class.clone()));
                    self.next_jump_id64 = last.id64;
                }
            let n = harvested.len();
            let mut asks = Vec::new();
            if n > 0 {
                let rows = harvested
                    .into_iter()
                    .filter_map(|h| {
                        Some(Hop { system: h.system?, star_class: h.star_class, x: None, y: None, z: None, id64: h.id64 })
                    })
                    .collect();
                asks.push(Ask::RecordSeen { rows, ts: None });
            }
            asks.push(Ask::PromoteConfirmed { only: Only::All });
            asks.push(Ask::RouteHops);
            self.ask(asks, Then::CaughtUp { harvested: n }, true, None);
            self.poll_navroute();
            match self.reader.prime() {
                Some(primed) => self.on_position(&primed, false),
                None => {
                    self.tables[SECT].blank();
                    let dir = self.args.journal_dir.display().to_string();
                    self.note(&format!("no Journal.*.log in {dir} -- is Elite installed and has it run?"), Role::Warn);
                    self.update_status();
                }
            }
        }
        self.register_hotkeys();
        if self.args.sector.is_none() {
            self.show_jump_range();
        }
        self.check_focus();
        self.redraw();
    }

    pub fn shutdown(&mut self) {
        self.lights.clear();
        hotkeys::unregister();
        self.worker.stop();
    }

    fn took_routes(&mut self, routes: BTreeMap<String, Vec<crate::database::RouteEnd>>) {
        for hops in routes.values() {
            let (Some(first), Some(last)) = (hops.first(), hops.last()) else { continue };
            for end in [first, last] {
                let label: String = ROUTE_ALIAS
                    .iter()
                    .find(|(s, _)| *s == end.system)
                    .map(|(_, l)| l.to_string())
                    .unwrap_or_else(|| end.system.split_whitespace().next().unwrap_or("").to_uppercase())
                    .chars()
                    .take(7)
                    .collect();
                if let Some(xyz) = end.xyz {
                    self.dests.insert(label, (end.system.clone(), xyz));
                }
            }
        }
        if self.dests.is_empty() {
            self.note("no destinations -- main.route is empty or not loaded yet", Role::Dim);
        } else {
            let list: Vec<String> = self.dests.iter().map(|(k, v)| format!("{k} = {}", v.0)).collect();
            say!("destinations: {}", list.join(", "));
        }
    }

    fn caught_up(&mut self, mut r: Results, harvested: usize) {
        if let Some(Answer::Routes(routes)) = r.remove("route_hops") {
            self.took_routes(routes);
        }
        if harvested > 0 {
            let new = match r.get("record_seen") {
                Some(Answer::Names(n)) => n.len(),
                _ => 0,
            };
            say!("harvested {harvested} revealed class(es) from the journal, {new} new");
        }
        if let Some(Answer::Count(n)) = r.get("promote_confirmed")
            && *n > 0 {
                say!("promoted {n} rare sighting(s) into the find log");
            }
        self.recount();
        self.solve_chains();
    }

    fn show_jump_range(&mut self) {
        let loadout = journal::read_loadout(&self.args.journal_dir);
        self.take_loadout(loadout);
    }

    fn take_loadout(&mut self, loadout: Option<Value>) {
        let Some(loadout) = loadout else { return };
        let was = self.jump_range;
        self.jump_range = ship::jump_range(&loadout);
        let text = ship::summary(&loadout);
        self.loadout = Some(loadout);
        if self.jump_range.is_none() || was == self.jump_range {
            return;
        }
        if let Some(t) = &text {
            say!("ship: {t}");
        }
        if was.is_some() {
            self.note(&format!("ship changed: {} -- re-plotting", text.unwrap_or_default()), Role::Ok);
        }
        self.unsolvable.clear();
        self.solve_chains();
    }

    fn register_hotkeys(&mut self) {
        for warning in hotkeys::load_bindings(&bindings_path()) {
            say!("hotkeys: {warning}");
        }
        main_window::refresh_settings();
        if self.args.no_hotkeys {
            say!("hotkeys disabled (--no-hotkeys)");
            return;
        }
        match hotkeys::register() {
            Ok(()) => {
                for (_, action) in hotkeys::BINDINGS {
                    say!("hotkeys: {} -> {}", hotkeys::binding(action), hotkeys::description(action));
                }
            }
            Err(e) => {
                say!("hotkey FAILED keyboard hook: {e}");
                self.note("no hotkeys -- the table still works", Role::Warn);
            }
        }
    }
}

fn now_secs() -> i64 {
    std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).map_or(0, |d| d.as_secs() as i64)
}

fn local_hh_mm() -> String {
    use windows::Win32::System::SystemInformation::GetLocalTime;
    let t = unsafe { GetLocalTime() };
    format!("{:02}:{:02}", t.wHour, t.wMinute)
}
