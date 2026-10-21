use std::collections::{BTreeMap, HashMap, HashSet};
use std::path::PathBuf;
use std::sync::mpsc::{self, Receiver, RecvTimeoutError, Sender};
use std::sync::{Arc, Mutex};
use std::thread::JoinHandle;
use std::time::Duration;

use crate::database::{self, AliasOutcome, Database, MapGrid, OutcomeRow, RegionExpected, RouteEnd, Settled, TradeRow};
use crate::journal::Hop;
use crate::neutron_route::ChainHop;
use crate::row::Row;
use crate::timing::Phases;

#[derive(Clone, Debug)]
pub enum Only {
    All,
    FromRecordSeen,
}

#[derive(Clone, Debug)]
pub enum Ask {
    ConfirmedTargets { pos: Option<[f64; 3]> },
    CarrierTargets { pos: Option<[f64; 3]>, limit: i64 },
    NeutronTargets { pos: Option<[f64; 3]>, limit: i64 },
    TraderTargets { pos: Option<[f64; 3]>, per_type: i64 },
    AdjacentSectors { sector: Option<String>, pos: Option<[f64; 3]>, limit: i64 },
    TopTargets { sector: String, limit: i64, pos: Option<[f64; 3]> },
    UnfoundTargets { sector: String, limit: i64, pos: Option<[f64; 3]> },
    SectorTotals { sector: String },
    RegionTotals { sector: String, pos: Option<[f64; 3]> },
    RegionExpected { catalogued: bool },
    SectorExpected { region_id: i64, catalogued: bool, column: &'static str, limit: i64 },
    MapGrid,
    TradeTargets { pos: [f64; 3] },
    OutcomeVisit { system: String, ts: Option<String> },
    OutcomeScan { system: String, body: String, star_type: String },
    OutcomeComplete { system: String },
    Outcomes,
    SectorSummary { sector: String },
    RecordArrival { system: String, ts: Option<String> },
    RecordSeen { rows: Vec<Hop>, ts: Option<String> },
    PromoteConfirmed { only: Only },
    PredictedBoxel { names: Vec<String> },
    SettledBy { names: Vec<String> },
    MarkWrong { system: String, source: String, sector: Option<String> },
    RecordAlias {
        system: String,
        canonical: String,
        id64: Option<i64>,
        xyz: [Option<f64>; 3],
        star_class: Option<String>,
        ts: String,
    },
    SolveRoute { origin: [f64; 3], dest: [f64; 3], jump_ly: f64, names: (String, String) },
    RouteHops,
    NeutronCorridor { start: [f64; 3], dest: [f64; 3], pad: f64 },
    Counts,
}

impl Ask {
    pub fn name(&self) -> &'static str {
        match self {
            Ask::ConfirmedTargets { .. } => "confirmed_targets",
            Ask::CarrierTargets { .. } => "carrier_targets",
            Ask::NeutronTargets { .. } => "neutron_targets",
            Ask::TraderTargets { .. } => "trader_targets",
            Ask::AdjacentSectors { .. } => "adjacent_sectors",
            Ask::TopTargets { .. } => "top_targets",
            Ask::UnfoundTargets { .. } => "unfound_targets",
            Ask::SectorTotals { .. } => "sector_totals",
            Ask::RegionTotals { .. } => "region_totals",
            Ask::RegionExpected { .. } => "region_expected",
            Ask::SectorExpected { .. } => "sector_expected",
            Ask::MapGrid => "map_grid",
            Ask::TradeTargets { .. } => "trade_targets",
            Ask::OutcomeVisit { .. } => "outcome_visit",
            Ask::OutcomeScan { .. } => "outcome_scan",
            Ask::OutcomeComplete { .. } => "outcome_complete",
            Ask::Outcomes => "outcomes",
            Ask::SectorSummary { .. } => "sector_summary",
            Ask::RecordArrival { .. } => "record_arrival",
            Ask::RecordSeen { .. } => "record_seen",
            Ask::PromoteConfirmed { .. } => "promote_confirmed",
            Ask::PredictedBoxel { .. } => "predicted_boxel",
            Ask::SettledBy { .. } => "settled_by",
            Ask::MarkWrong { .. } => "mark_wrong",
            Ask::RecordAlias { .. } => "record_alias",
            Ask::SolveRoute { .. } => "solve_route",
            Ask::RouteHops => "route_hops",
            Ask::NeutronCorridor { .. } => "neutron_corridor",
            Ask::Counts => "counts",
        }
    }
}

#[derive(Clone, Debug)]
pub enum Answer {
    Rows(Vec<Row>),
    MaybeRows(Option<Vec<Row>>),
    Summary([i64; 4]),
    Arrival(Option<String>),
    Names(Vec<String>),
    Count(i64),
    NameSet(HashSet<String>),
    Settled(Vec<Settled>),
    Bool(bool),
    Alias(AliasOutcome),
    Chain(Option<Vec<ChainHop>>),
    Routes(BTreeMap<String, Vec<RouteEnd>>),
    Points(Vec<String>, Vec<[f64; 3]>),
    Counts(BTreeMap<String, i64>),
    Regions(Vec<RegionExpected>),
    Map(Box<MapGrid>),
    Trade(Vec<TradeRow>),
    Outcomes(Vec<OutcomeRow>),
}

pub type Results = HashMap<&'static str, Answer>;

struct Request {
    req_id: u64,
    asks: Vec<Ask>,
    write: bool,
    key: Option<String>,
}

pub struct DbWorker {
    tx: Option<Sender<Request>>,
    rx: Receiver<(u64, Result<Results, String>)>,
    newest: Arc<Mutex<HashMap<String, u64>>>,
    thread: Option<JoinHandle<()>>,
}

impl DbWorker {
    pub fn start(state: PathBuf, model: PathBuf, idle_seconds: f64, slow_ms: i64) -> DbWorker {
        let (tx, rx_in) = mpsc::channel::<Request>();
        let (tx_out, rx) = mpsc::channel();
        let newest: Arc<Mutex<HashMap<String, u64>>> = Arc::default();
        let seen = Arc::clone(&newest);
        let thread = std::thread::Builder::new()
            .name("db".into())
            .spawn(move || {
                let mut db = Database::new(&state, &model, Phases::new(slow_ms, "[db] "));
                loop {
                    let req = match rx_in.recv_timeout(Duration::from_secs(1)) {
                        Ok(req) => req,
                        Err(RecvTimeoutError::Timeout) => {
                            db.release_if_idle(idle_seconds);
                            continue;
                        }
                        Err(RecvTimeoutError::Disconnected) => break,
                    };
                    if let Some(key) = &req.key
                        && seen.lock().unwrap().get(key).is_some_and(|&n| n != req.req_id) {
                            continue;
                        }
                    let timing = db.timing.clone();
                    let result = {
                        let _span = timing.span("db");
                        std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| serve(&mut db, &req)))
                            .unwrap_or_else(|p| Err(panic_text(&p)))
                    };
                    if tx_out.send((req.req_id, result)).is_err() {
                        break;
                    }
                }
                db.close();
            })
            .expect("cannot start the database thread");
        DbWorker { tx: Some(tx), rx, newest, thread: Some(thread) }
    }

    pub fn submit(&self, req_id: u64, asks: Vec<Ask>, write: bool, key: Option<String>) {
        if let Some(k) = &key {
            self.newest.lock().unwrap().insert(k.clone(), req_id);
        }
        if let Some(tx) = &self.tx {
            let _ = tx.send(Request { req_id, asks, write, key });
        }
    }

    pub fn drain(&self) -> Vec<(u64, Result<Results, String>)> {
        self.rx.try_iter().collect()
    }

    pub fn stop(&mut self) {
        self.tx = None;
        if let Some(t) = self.thread.take() {
            let _ = t.join();
        }
    }
}

impl Drop for DbWorker {
    fn drop(&mut self) {
        self.stop();
    }
}

pub fn panic_text(p: &Box<dyn std::any::Any + Send>) -> String {
    p.downcast_ref::<String>()
        .cloned()
        .or_else(|| p.downcast_ref::<&str>().map(|s| s.to_string()))
        .unwrap_or_else(|| "panic".into())
}

fn serve(db: &mut Database, req: &Request) -> Result<Results, String> {
    if !req.write {
        let wrote: Vec<&str> =
            req.asks.iter().map(Ask::name).filter(|n| database::WRITES.contains(n)).collect();
        if !wrote.is_empty() {
            return Err(format!("write method in a read request: {wrote:?}"));
        }
    }
    let mut results = Results::new();
    for ask in &req.asks {
        let answer = run(db, ask, &results).map_err(|e| format!("{}: {e}", ask.name()))?;
        results.insert(ask.name(), answer);
    }
    Ok(results)
}

fn run(db: &mut Database, ask: &Ask, done: &Results) -> Result<Answer, String> {
    Ok(match ask {
        Ask::ConfirmedTargets { pos } => Answer::Rows(db.confirmed_targets(*pos)?),
        Ask::CarrierTargets { pos, limit } => Answer::Rows(db.carrier_targets(*pos, *limit)?),
        Ask::NeutronTargets { pos, limit } => Answer::Rows(db.neutron_targets(*pos, *limit)?),
        Ask::TraderTargets { pos, per_type } => Answer::Rows(db.trader_targets(*pos, *per_type)?),
        Ask::AdjacentSectors { sector, pos, limit } => {
            Answer::Rows(db.adjacent_sectors(sector.as_deref(), *pos, *limit)?)
        }
        Ask::TopTargets { sector, limit, pos } => Answer::Rows(db.top_targets(sector, *limit, *pos)?),
        Ask::UnfoundTargets { sector, limit, pos } => Answer::Rows(db.unfound_targets(sector, *limit, *pos)?),
        Ask::SectorTotals { sector } => Answer::Rows(db.sector_totals(sector)?),
        Ask::RegionTotals { sector, pos } => Answer::MaybeRows(db.region_totals(sector, *pos)?),
        Ask::RegionExpected { catalogued } => Answer::Regions(db.region_expected(*catalogued)?),
        Ask::SectorExpected { region_id, catalogued, column, limit } => {
            Answer::Regions(db.sector_expected(*region_id, *catalogued, column, *limit)?)
        }
        Ask::MapGrid => Answer::Map(Box::new(db.map_grid()?)),
        Ask::TradeTargets { pos } => Answer::Trade(db.trade_targets(*pos)?),
        Ask::OutcomeVisit { system, ts } => Answer::Count(db.outcome_visit(system, ts.as_deref())? as i64),
        Ask::OutcomeScan { system, body, star_type } => Answer::Count(db.outcome_scan(system, body, star_type)? as i64),
        Ask::OutcomeComplete { system } => Answer::Count(db.outcome_complete(system)? as i64),
        Ask::Outcomes => Answer::Outcomes(db.outcomes()?),
        Ask::SectorSummary { sector } => Answer::Summary(db.sector_summary(sector)?),
        Ask::RecordArrival { system, ts } => {
            Answer::Arrival(db.record_arrival(system, ts.as_deref())?)
        }
        Ask::RecordSeen { rows, ts } => Answer::Names(db.record_seen(rows, ts.as_deref())?),
        Ask::PromoteConfirmed { only } => match only {
            Only::All => Answer::Count(db.promote_confirmed(None)?),
            Only::FromRecordSeen => {
                let Some(Answer::Names(names)) = done.get("record_seen") else {
                    return Err("promote_confirmed asked for record_seen's answer before it ran".into());
                };
                Answer::Count(db.promote_confirmed(Some(names))?)
            }
        },
        Ask::PredictedBoxel { names } => Answer::NameSet(db.predicted_boxel(names)?),
        Ask::SettledBy { names } => Answer::Settled(db.settled_by(names)?),
        Ask::MarkWrong { system, source, sector } => Answer::Bool(db.mark_wrong(system, source, sector.as_deref())?),
        Ask::RecordAlias { system, canonical, id64, xyz, star_class, ts } => {
            Answer::Alias(db.record_alias(system, canonical, *id64, *xyz, star_class.as_deref(), ts)?)
        }
        Ask::SolveRoute { origin, dest, jump_ly, names } => {
            Answer::Chain(db.solve_route(*origin, *dest, *jump_ly, (&names.0, &names.1))?)
        }
        Ask::RouteHops => Answer::Routes(db.route_hops()?),
        Ask::NeutronCorridor { start, dest, pad } => {
            let (names, pts) = db.neutron_corridor(*start, *dest, *pad)?;
            Answer::Points(names, pts)
        }
        Ask::Counts => Answer::Counts(db.counts()?),
    })
}
