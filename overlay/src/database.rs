use std::collections::{BTreeMap, HashMap, HashSet};
use std::path::{Path, PathBuf};
use std::time::Instant;

use duckdb::types::Value;
use duckdb::{Connection, params_from_iter};

use crate::journal::Hop;
use crate::kinds::{self, KINDS};
use crate::neutron_route::{self, ChainHop, Corridor};
use crate::route::dist;
use crate::row::*;
use crate::timing::Phases;

pub type DbResult<T> = Result<T, String>;

const MODEL: &str = "mdl.model";
const MIN_RARE: &str = "0.01";
const CARRIER_FRESH_DAYS: &str = "7";
pub const CARRIER_RANGE_LY: f64 = 500.0;
const CARRIER_SAME_LY: &str = "0.5";
const MAX_POI_ROWS: &str = "3";
pub const SECTOR_CANDIDATES: usize = 10;
const MAX_OVER: u32 = 4;
const CATALOGUED_LABEL: &str = "  + PLOT ONLY";
const LIST_SEP: char = '\u{1f}';

macro_rules! sql_files {
    ($($name:literal),* $(,)?) => {
        &[$(($name, include_str!(concat!("../sql/", $name, ".sql")))),*]
    };
}

const SQL: &[(&str, &str)] = sql_files!(
    "boxel_id64",
    "confirmed_cte",
    "confirmed_targets",
    "top_targets",
    "unfound_targets",
    "adjacent_sectors",
    "sector_totals",
    "region_totals",
    "region_expected",
    "sector_expected",
    "sector_best",
    "carrier_next",
    "system_pos",
    "carrier_destination",
    "carrier_destination_set",
    "trade_targets",
    "outcome_visit",
    "outcome_scan",
    "outcome_complete",
    "outcomes",
    "map_regions",
    "map_density",
    "region_of",
    "sector_summary",
    "poi_in_system",
    "carrier_targets",
    "neutron_targets",
    "trader_targets",
    "promote_confirmed",
    "neutron_corridor",
    "chain_corridor",
    "settled_by",
    "predicted_boxel",
    "record_arrival",
    "record_seen",
    "record_alias",
    "mark_wrong",
    "route_hops",
    "counts",
    "connect",
    "seed_state",
);

pub const WRITES: [&str; 10] = [
    "record_arrival",
    "record_seen",
    "record_poi_visit",
    "mark_wrong",
    "promote_confirmed",
    "record_alias",
    "outcome_visit",
    "outcome_scan",
    "outcome_complete",
    "carrier_destination_set",
];

const OUTCOME_DDL: &str = include_str!("../../schema/system_outcome.sql");
const CARRIER_DESTINATION_DDL: &str = include_str!("../../schema/carrier_destination.sql");

pub fn found_column(column: &str) -> String {
    format!("found_{}", column.trim_start_matches("p_"))
}

fn quoted(items: impl IntoIterator<Item = String>) -> String {
    items.into_iter().map(|s| format!("'{}'", s.replace('\'', "''"))).collect::<Vec<_>>().join(", ")
}

fn fragments() -> HashMap<&'static str, String> {
    let ranking: Vec<&str> = KINDS.iter().filter(|k| k.ranks).map(|k| k.column).collect();
    let rare: Vec<&str> = KINDS.iter().filter(|k| k.rare).map(|k| k.column).collect();
    let cols: Vec<&str> = KINDS.iter().map(|k| k.column).collect();
    let prefixed = |p: &str, list: &[&str]| list.iter().map(|c| format!("{p}{c}")).collect::<Vec<_>>().join(", ");
    let class_case = KINDS
        .iter()
        .map(|k| {
            format!(
                "WHEN star_class IN ({}) THEN '{}'",
                quoted(k.classes.iter().map(|c| c.to_string())),
                k.key
            )
        })
        .collect::<Vec<_>>()
        .join(" ");
    let abbr_case =
        KINDS.iter().map(|k| format!("WHEN kind = '{}' THEN '{}'", k.key, k.abbr)).collect::<Vec<_>>().join(" ");
    let rank_case = KINDS
        .iter()
        .enumerate()
        .map(|(i, k)| format!("WHEN kind = '{}' THEN {i}", k.key))
        .collect::<Vec<_>>()
        .join(" ");
    let mut f = HashMap::new();
    f.insert("MODEL", MODEL.to_string());
    f.insert("CLASS_CASE", class_case);
    f.insert("ALL_CLASSES", quoted(kinds::all_classes().into_iter().map(String::from)));
    f.insert("ABBR_CASE", abbr_case);
    f.insert("RANK_CASE", rank_case);
    f.insert("RANK_BY", format!("greatest({})", prefixed("p.", &ranking)));
    f.insert("RANK_BY_BARE", format!("greatest({})", ranking.join(", ")));
    f.insert("RARE_MAX", prefixed("p.", &rare));
    f.insert("P_COLUMNS", cols.join(", "));
    f.insert("P_COLUMNS_P", prefixed("p.", &cols));
    f.insert("P_COLUMNS_N", prefixed("n.", &cols));
    f.insert("P_NULLS", cols.iter().map(|c| format!("NULL::DOUBLE AS {c}")).collect::<Vec<_>>().join(", "));
    f.insert("P_SUMS", cols.iter().map(|c| format!("sum(p.{c}) AS {c}")).collect::<Vec<_>>().join(", "));
    f.insert(
        "P_PICK",
        format!(
            "CASE ? {} END",
            cols.iter().map(|c| format!("WHEN '{c}' THEN p.{c}")).collect::<Vec<_>>().join(" ")
        ),
    );
    f.insert(
        "P_ORDER",
        format!(
            "CASE ? {} END",
            cols.iter().map(|c| format!("WHEN '{c}' THEN sum(p.{c})")).collect::<Vec<_>>().join(" ")
        ),
    );
    let found: Vec<String> = cols.iter().map(|c| found_column(c)).collect();
    f.insert("FOUND_COLUMNS", found.join(", "));
    f.insert("FOUND_FALSE", vec!["false"; found.len()].join(", "));
    f.insert(
        "FOUND_UPDATE",
        KINDS
            .iter()
            .zip(&found)
            .map(|(k, f)| format!("{f} = o.{f} OR s.cls IN ({})", quoted(k.classes.iter().map(|c| c.to_string()))))
            .collect::<Vec<_>>()
            .join(",\n    "),
    );
    f.insert("P_SUMS_BARE", cols.iter().map(|c| format!("sum({c}) AS {c}")).collect::<Vec<_>>().join(", "));
    f.insert("SEEN_CLASS", "coalesce(s.star_class, si.star_class, sa.star_class)".to_string());
    f.insert(
        "SEEN_JOIN",
        "LEFT JOIN system_seen s ON s.system = p.system \
         LEFT JOIN system_seen si ON si.system_id = {{BOXEL_ID64}} \
         LEFT JOIN system_alias al ON al.system = p.system \
         LEFT JOIN system_seen sa ON sa.system = al.canonical"
            .to_string(),
    );
    f.insert("MIN_RARE", MIN_RARE.to_string());
    f.insert("CARRIER_FRESH_DAYS", CARRIER_FRESH_DAYS.to_string());
    f.insert("CARRIER_RANGE_LY", format!("{CARRIER_RANGE_LY:.1}"));
    f.insert("CARRIER_SAME_LY", CARRIER_SAME_LY.to_string());
    f.insert("MAX_POI_ROWS", MAX_POI_ROWS.to_string());
    f.insert("SECTOR_CANDIDATES", SECTOR_CANDIDATES.to_string());
    f.insert("NEUTRON_ABBR", kinds::by_key("NEUTRON").abbr.to_string());
    for (name, value) in [
        ("ROW_CONFIRMED", ROW_CONFIRMED),
        ("ROW_POI", ROW_POI),
        ("ROW_PREDICTED", ROW_PREDICTED),
        ("ROW_CATALOG", ROW_CATALOG),
        ("ROW_CARRIER", ROW_CARRIER),
        ("ROW_SECTOR", ROW_SECTOR),
        ("ROW_NEUTRON", ROW_NEUTRON),
        ("ROW_UNFOUND", ROW_UNFOUND),
        ("ROW_TRADER", ROW_TRADER),
    ] {
        f.insert(name, value.to_string());
    }
    f
}

fn render(text: &str, f: &HashMap<&'static str, String>) -> String {
    let mut out = String::with_capacity(text.len() * 2);
    let mut rest = text;
    while let Some(at) = rest.find("{{") {
        out.push_str(&rest[..at]);
        let end = rest[at..].find("}}").expect("unclosed {{ in a .sql file") + at;
        let key = &rest[at + 2..end];
        out.push_str(f.get(key).unwrap_or_else(|| panic!("no SQL fragment named {key}")));
        rest = &rest[end + 2..];
    }
    out.push_str(rest);
    out
}

pub fn rendered_sql() -> HashMap<&'static str, Vec<String>> {
    let mut f = fragments();
    let boxel = SQL.iter().find(|(n, _)| *n == "boxel_id64").unwrap().1.trim().to_string();
    let seen_join = render(&f["SEEN_JOIN"], &HashMap::from([("BOXEL_ID64", boxel)]));
    f.insert("SEEN_JOIN", seen_join);
    let cte = SQL.iter().find(|(n, _)| *n == "confirmed_cte").unwrap().1;
    let cte = render(cte, &f);
    f.insert("CONFIRMED_CTE", cte);
    SQL.iter()
        .map(|(name, text)| {
            let stmts = render(text, &f)
                .split(";\n")
                .map(str::trim)
                .filter(|s| !s.is_empty())
                .map(|s| s.trim_end_matches(';').to_string())
                .collect();
            (*name, stmts)
        })
        .collect()
}

fn cell(v: Value) -> Cell {
    match v {
        Value::Null => Cell::Null,
        Value::Boolean(b) => Cell::Bool(b),
        Value::TinyInt(i) => Cell::Int(i as i64),
        Value::SmallInt(i) => Cell::Int(i as i64),
        Value::Int(i) => Cell::Int(i as i64),
        Value::BigInt(i) => Cell::Int(i),
        Value::HugeInt(i) => Cell::Int(i as i64),
        Value::UTinyInt(i) => Cell::Int(i as i64),
        Value::USmallInt(i) => Cell::Int(i as i64),
        Value::UInt(i) => Cell::Int(i as i64),
        Value::UBigInt(i) => Cell::Int(i as i64),
        Value::Float(f) => Cell::Float(f as f64),
        Value::Double(f) => Cell::Float(f),
        Value::Text(s) => Cell::Text(s),
        Value::List(items) => Cell::List(items.into_iter().map(cell).collect()),
        other => Cell::Text(format!("{other:?}")),
    }
}

fn opt_f(v: Option<f64>) -> Value {
    v.map_or(Value::Null, Value::Double)
}

fn opt_s(v: Option<&str>) -> Value {
    v.map_or(Value::Null, |s| Value::Text(s.to_string()))
}

fn s(v: &str) -> Value {
    Value::Text(v.to_string())
}

fn pos_params(pos: Option<[f64; 3]>) -> Vec<Value> {
    match pos {
        Some(p) => p.iter().map(|v| Value::Double(*v)).collect(),
        None => vec![Value::Null, Value::Null, Value::Null],
    }
}

fn joined(names: &[String]) -> Value {
    Value::Text(names.join(&LIST_SEP.to_string()))
}

#[derive(Clone, Debug)]
pub struct Settled {
    pub system: String,
    pub sector: Option<String>,
    pub is_catalog: bool,
    pub was_classed: Option<String>,
}

#[derive(Clone, Debug)]
pub struct RegionExpected {
    pub region: String,
    pub id: Option<i64>,
    pub systems: i64,
    pub known: i64,
    pub p: [f64; KINDS.len()],
}

#[derive(Clone, Debug)]
pub struct CarrierView {
    pub pos: Option<[f64; 3]>,
    pub hop: Option<CarrierHop>,
}

#[derive(Clone, Debug)]
pub struct CarrierHop {
    pub target_pos: [f64; 3],
    pub next: Option<(String, f64, f64)>,
}

#[derive(Clone, Debug)]
pub struct TradeRow {
    pub kind: String,
    pub system: String,
    pub station: String,
    pub dist_ly: Option<f64>,
    pub arrival_ls: Option<f64>,
    pub note: Option<String>,
}

#[derive(Clone, Debug)]
pub struct OutcomeRow {
    pub system: String,
    pub visited: String,
    pub is_catalog: bool,
    pub p: [Option<f64>; KINDS.len()],
    pub found: [bool; KINDS.len()],
    pub stars: i64,
    pub complete: bool,
}

pub const MAP_GRID: usize = 2048;
pub const DENSITY_GRID: usize = 1024;

#[derive(Clone)]
pub struct MapGrid {
    pub regions: Vec<u8>,
    pub density: Vec<u32>,
}

impl std::fmt::Debug for MapGrid {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "MapGrid({}x{} regions, {}x{} density)", MAP_GRID, MAP_GRID, DENSITY_GRID, DENSITY_GRID)
    }
}

#[derive(Clone, Debug)]
pub struct RouteEnd {
    pub system: String,
    pub xyz: Option<[f64; 3]>,
}

#[derive(Clone, Debug)]
pub enum AliasOutcome {
    Recorded,
    Unchanged,
    HeldBy(String),
}

pub struct Database {
    state: PathBuf,
    model: PathBuf,
    sql: HashMap<&'static str, Vec<String>>,
    con: Option<Connection>,
    last_used: Instant,
    pub timing: Phases,
}

impl Database {
    pub fn new(state: &Path, model: &Path, timing: Phases) -> Database {
        Database {
            state: state.to_path_buf(),
            model: model.to_path_buf(),
            sql: rendered_sql(),
            con: None,
            last_used: Instant::now(),
            timing,
        }
    }

    fn stmt(&self, name: &str, i: usize) -> &str {
        &self.sql.get(name).unwrap_or_else(|| panic!("no SQL named {name}"))[i]
    }

    fn connection(&mut self) -> DbResult<&Connection> {
        if self.con.is_none() {
            let _p = self.timing.phase("db_connect");
            self.con = Some(open(&self.state, &self.model, &self.sql)?);
        }
        self.last_used = Instant::now();
        Ok(self.con.as_ref().unwrap())
    }

    pub fn release_if_idle(&mut self, seconds: f64) -> bool {
        if self.con.is_none() || self.last_used.elapsed().as_secs_f64() < seconds {
            return false;
        }
        self.close();
        true
    }

    pub fn close(&mut self) {
        self.con = None;
    }

    fn rows(&mut self, name: &str, i: usize, params: Vec<Value>) -> DbResult<Vec<Row>> {
        let sql = self.stmt(name, i).to_string();
        let (names, cells) = query(self.connection()?, &sql, params)?;
        cells.into_iter().map(|c| Row::from_cells(&names, c)).collect()
    }

    fn table(&mut self, name: &str, i: usize, params: Vec<Value>) -> DbResult<Vec<Vec<Cell>>> {
        let sql = self.stmt(name, i).to_string();
        Ok(query(self.connection()?, &sql, params)?.1)
    }

    fn one(&mut self, name: &str, i: usize, params: Vec<Value>) -> DbResult<Option<Vec<Cell>>> {
        Ok(self.table(name, i, params)?.into_iter().next())
    }

    fn count(&mut self, name: &str, i: usize, params: Vec<Value>) -> DbResult<i64> {
        Ok(self.one(name, i, params)?.and_then(|r| r[0].int()).unwrap_or(0))
    }

    fn exec(&mut self, name: &str, i: usize, params: Vec<Value>) -> DbResult<usize> {
        let sql = self.stmt(name, i).to_string();
        let con = self.connection()?;
        let mut stmt = con.prepare(&sql).map_err(|e| e.to_string())?;
        stmt.execute(params_from_iter(params)).map_err(|e| e.to_string())
    }

    pub fn confirmed_targets(&mut self, pos: Option<[f64; 3]>) -> DbResult<Vec<Row>> {
        self.rows("confirmed_targets", 0, pos_params(pos))
    }

    pub fn top_targets(&mut self, sector: &str, limit: i64, pos: Option<[f64; 3]>) -> DbResult<Vec<Row>> {
        let mut p = vec![s(sector), s(sector)];
        p.extend(pos_params(pos));
        p.extend(pos_params(pos));
        p.push(Value::BigInt(limit));
        self.rows("top_targets", 0, p)
    }

    pub fn unfound_targets(&mut self, sector: &str, limit: i64, pos: Option<[f64; 3]>) -> DbResult<Vec<Row>> {
        if sector.is_empty() {
            return Ok(Vec::new());
        }
        let mut p = pos_params(pos);
        p.push(s(sector));
        p.push(Value::BigInt(limit));
        self.rows("unfound_targets", 0, p)
    }

    pub fn mark_wrong(&mut self, system: &str, source: &str, sector: Option<&str>) -> DbResult<bool> {
        let stamp = crate::log::utc_stamp().replace(' ', "T");
        if self.count("mark_wrong", 0, vec![s(system)])? > 0 {
            return Ok(false);
        }
        self.exec(
            "mark_wrong",
            1,
            vec![s(system), s(source), opt_s(sector), s(system), Value::Text(stamp), Value::Null],
        )?;
        Ok(true)
    }

    fn totals_row(label: &str, n: i64, sums: [Option<f64>; KINDS.len()], catalogued: bool) -> Row {
        Row {
            n: Some(n),
            system: Some(label.to_string()),
            type_label: Some(format!("\u{3a3} {}", crate::table::thousands_i(n))),
            row_grp: Some(if catalogued { ROW_TOTAL_CATALOG } else { ROW_TOTAL }),
            p: sums,
            ..Row::default()
        }
    }

    fn totals_pair(&mut self, label: &str, name: &str, key: Value) -> DbResult<Vec<Row>> {
        let table = self.table(name, 0, vec![key])?;
        let mut out = Vec::new();
        for (is_cat, text) in [(false, label), (true, CATALOGUED_LABEL)] {
            let got = table.iter().find(|r| r[0].bool() == is_cat);
            let n = got.and_then(|r| r[1].int()).unwrap_or(0);
            let mut sums = [None; KINDS.len()];
            if let Some(r) = got {
                for (i, slot) in sums.iter_mut().enumerate() {
                    *slot = r[2 + i].float();
                }
            }
            out.push(Self::totals_row(text, n, sums, is_cat));
        }
        Ok(out)
    }

    pub fn sector_totals(&mut self, sector: &str) -> DbResult<Vec<Row>> {
        self.totals_pair(&format!("SECTOR {sector}"), "sector_totals", s(sector))
    }

    pub fn region_totals(&mut self, sector: &str, pos: Option<[f64; 3]>) -> DbResult<Option<Vec<Row>>> {
        let (x, z) = (opt_f(pos.map(|p| p[0])), opt_f(pos.map(|p| p[2])));
        let Some(found) = self.one("region_of", 0, vec![s(sector), z, x])? else {
            return Ok(None);
        };
        let (Some(region_id), Some(region)) = (found[0].int(), found[1].text()) else {
            return Ok(None);
        };
        let mut rows = self.totals_pair(&format!("REGION {region}"), "region_totals", Value::BigInt(region_id))?;
        for row in rows.iter_mut().filter(|r| r.row_grp == Some(ROW_TOTAL)) {
            row.row_grp = Some(ROW_REGION);
        }
        Ok(Some(rows))
    }

    fn expected_rows(table: Vec<Vec<Cell>>) -> Vec<RegionExpected> {
        table
            .into_iter()
            .map(|r| {
                let mut p = [0.0; KINDS.len()];
                for (i, slot) in p.iter_mut().enumerate() {
                    *slot = r[3 + i].float().unwrap_or(0.0);
                }
                RegionExpected {
                    region: r[0].text().unwrap_or_default(),
                    id: r.get(3 + KINDS.len()).and_then(Cell::int),
                    systems: r[1].int().unwrap_or(0),
                    known: r[2].int().unwrap_or(0),
                    p,
                }
            })
            .collect()
    }

    pub fn region_expected(&mut self, catalogued: bool) -> DbResult<Vec<RegionExpected>> {
        let _p = self.timing.phase("region_expected");
        Ok(Self::expected_rows(self.table("region_expected", 0, vec![Value::Boolean(catalogued)])?))
    }

    pub fn sector_expected(
        &mut self,
        region_id: i64,
        catalogued: bool,
        column: &str,
        limit: i64,
    ) -> DbResult<Vec<RegionExpected>> {
        let _p = self.timing.phase("sector_expected");
        let params = vec![Value::BigInt(region_id), Value::Boolean(catalogued), s(column), Value::BigInt(limit)];
        Ok(Self::expected_rows(self.table("sector_expected", 0, params)?))
    }

    pub fn sector_best(&mut self, sector: &str, column: &str, catalogued: bool) -> DbResult<Option<(String, Option<f64>)>> {
        let params = vec![s(column), s(sector), Value::Boolean(catalogued)];
        Ok(self.one("sector_best", 0, params)?.and_then(|r| r[0].text().map(|system| (system, r[1].float()))))
    }

    pub fn system_pos(&mut self, system: &str, system_id: Option<i64>) -> DbResult<Option<[f64; 3]>> {
        let id = system_id.map_or(Value::Null, Value::BigInt);
        let params = vec![s(system), id.clone(), id, s(system), s(system)];
        Ok(self.one("system_pos", 0, params)?.and_then(|r| Some([r[0].float()?, r[1].float()?, r[2].float()?])))
    }

    pub fn carrier_view(
        &mut self,
        system: &str,
        system_id: Option<i64>,
        pos: Option<[f64; 3]>,
        target: Option<&str>,
    ) -> DbResult<CarrierView> {
        let pos = match pos {
            Some(p) => Some(p),
            None => self.system_pos(system, system_id)?,
        };
        let hop = match (pos, target) {
            (Some(p), Some(t)) => self.carrier_next(t, p)?,
            _ => None,
        };
        Ok(CarrierView { pos, hop })
    }

    pub fn carrier_destination(&mut self) -> DbResult<Option<String>> {
        Ok(self.one("carrier_destination", 0, Vec::new())?.and_then(|r| r[0].text()))
    }

    pub fn set_carrier_destination(&mut self, callsign: &str, destination: &str) -> DbResult<usize> {
        self.exec("carrier_destination_set", 0, vec![s(callsign), s(destination)])
    }

    pub fn carrier_next(&mut self, target: &str, carrier: [f64; 3]) -> DbResult<Option<CarrierHop>> {
        let params = vec![
            s(target),
            s(target),
            s(target),
            Value::Double(carrier[0]),
            Value::Double(carrier[1]),
            Value::Double(carrier[2]),
            s(target),
        ];
        let Some(r) = self.one("carrier_next", 0, params)? else { return Ok(None) };
        let (Some(x), Some(y), Some(z)) = (r[0].float(), r[1].float(), r[2].float()) else { return Ok(None) };
        let next = match (r[3].text(), r[4].float(), r[5].float()) {
            (Some(system), Some(jump), Some(left)) => Some((system, jump, left)),
            _ => None,
        };
        Ok(Some(CarrierHop { target_pos: [x, y, z], next }))
    }

    pub fn trade_targets(&mut self, pos: [f64; 3]) -> DbResult<Vec<TradeRow>> {
        let params = pos.iter().map(|&v| Value::Double(v)).collect();
        let mut rows: Vec<TradeRow> = self
            .table("trade_targets", 0, params)?
            .into_iter()
            .map(|r| TradeRow {
                kind: r[0].text().unwrap_or_default(),
                system: r[1].text().unwrap_or_default(),
                station: r[2].text().unwrap_or_default(),
                dist_ly: r[3].float(),
                arrival_ls: r[4].float(),
                note: None,
            })
            .collect();
        let after_brokers = rows.iter().rposition(|r| r.kind.ends_with("tech broker")).map_or(rows.len(), |i| i + 1);
        if let Some(sirius) = crate::sirius::nearest(pos) {
            rows.insert(after_brokers, sirius);
        }
        Ok(rows)
    }

    pub fn outcome_visit(&mut self, system: &str, ts: Option<&str>) -> DbResult<usize> {
        self.exec("outcome_visit", 0, vec![opt_s(ts), s(system)])
    }

    pub fn outcome_scan(&mut self, system: &str, body: &str, star_type: &str) -> DbResult<usize> {
        self.exec("outcome_scan", 0, vec![s(system), s(body), s(star_type)])
    }

    pub fn outcome_complete(&mut self, system: &str) -> DbResult<usize> {
        self.exec("outcome_complete", 0, vec![s(system)])
    }

    pub fn outcomes(&mut self) -> DbResult<Vec<OutcomeRow>> {
        let n = KINDS.len();
        Ok(self
            .table("outcomes", 0, Vec::new())?
            .into_iter()
            .map(|r| {
                let mut p = [None; KINDS.len()];
                let mut found = [false; KINDS.len()];
                for i in 0..n {
                    p[i] = r[3 + i].float();
                    found[i] = r[3 + n + i].bool();
                }
                OutcomeRow {
                    system: r[0].text().unwrap_or_default(),
                    visited: r[1].text().unwrap_or_default(),
                    is_catalog: r[2].bool(),
                    p,
                    found,
                    stars: r[3 + 2 * n].int().unwrap_or(0),
                    complete: r[4 + 2 * n].bool(),
                }
            })
            .collect())
    }

    pub fn map_grid(&mut self) -> DbResult<MapGrid> {
        let _p = self.timing.phase("map_grid");
        let mut regions = vec![0u8; MAP_GRID * MAP_GRID];
        for r in self.table("map_regions", 0, Vec::new())? {
            let (Some(z), Some(x), Some(len), Some(id)) = (r[0].int(), r[1].int(), r[2].int(), r[3].int()) else {
                continue;
            };
            let start = z as usize * MAP_GRID + x as usize;
            let end = (start + len as usize).min((z as usize + 1) * MAP_GRID);
            regions[start..end].fill(id as u8);
        }
        let mut density = vec![0u32; DENSITY_GRID * DENSITY_GRID];
        for r in self.table("map_density", 0, Vec::new())? {
            let (Some(x), Some(z), Some(n)) = (r[0].int(), r[1].int(), r[2].int()) else { continue };
            if (0..DENSITY_GRID as i64).contains(&x) && (0..DENSITY_GRID as i64).contains(&z) {
                density[z as usize * DENSITY_GRID + x as usize] = n.min(u32::MAX as i64) as u32;
            }
        }
        Ok(MapGrid { regions, density })
    }

    pub fn adjacent_sectors(
        &mut self,
        sector: Option<&str>,
        pos: Option<[f64; 3]>,
        limit: i64,
    ) -> DbResult<Vec<Row>> {
        if pos.is_none() {
            return Ok(Vec::new());
        }
        let mut p = vec![opt_s(sector)];
        p.extend(pos_params(pos));
        p.push(Value::BigInt(limit));
        self.rows("adjacent_sectors", 0, p)
    }

    pub fn sector_summary(&mut self, sector: &str) -> DbResult<[i64; 4]> {
        let r = self.one("sector_summary", 0, vec![s(sector)])?.unwrap_or_default();
        let at = |i: usize| r.get(i).and_then(Cell::int).unwrap_or(0);
        Ok([at(0), at(1), at(2), at(3)])
    }

    pub fn poi_in_system(&mut self, system: &str) -> DbResult<Option<(i64, String, String)>> {
        Ok(self.one("poi_in_system", 0, vec![s(system)])?.and_then(|r| {
            Some((r[0].int()?, r[1].text().unwrap_or_default(), r[2].text().unwrap_or_default()))
        }))
    }

    pub fn record_arrival(&mut self, system: &str, ts: Option<&str>) -> DbResult<Option<String>> {
        let new = self.count("record_arrival", 0, vec![s(system)])? == 0;
        if new {
            self.exec("record_arrival", 1, vec![s(system), s(system), opt_s(ts), opt_s(ts)])?;
        } else if ts.is_some() {
            self.exec("record_arrival", 2, vec![opt_s(ts), s(system)])?;
        }
        let mut poi = None;
        if self.count("record_arrival", 3, vec![s(system)])? == 0
            && let Some((poi_id, name, class)) = self.poi_in_system(system)? {
                self.exec(
                    "record_arrival",
                    4,
                    vec![s(system), s(system), Value::BigInt(poi_id), s(&name), s(&class), opt_s(ts)],
                )?;
                poi = Some(name);
            }
        Ok(poi)
    }

    pub fn record_seen(&mut self, rows: &[Hop], ts: Option<&str>) -> DbResult<Vec<String>> {
        let rows: Vec<&Hop> = rows.iter().filter(|r| !r.system.is_empty()).collect();
        if rows.is_empty() {
            return Ok(Vec::new());
        }
        self.exec("record_seen", 0, vec![])?;
        for r in &rows {
            self.exec(
                "record_seen",
                1,
                vec![
                    s(&r.system),
                    opt_s(r.star_class.as_deref()),
                    opt_f(r.x),
                    opt_f(r.y),
                    opt_f(r.z),
                    r.id64.map_or(Value::Null, Value::BigInt),
                ],
            )?;
        }
        self.exec("record_seen", 2, vec![])?;
        self.exec("record_seen", 3, vec![])?;
        let new: Vec<String> =
            self.table("record_seen", 4, vec![])?.into_iter().filter_map(|r| r[0].text()).collect();
        if !new.is_empty() {
            self.exec("record_seen", 5, vec![opt_s(ts)])?;
            let _p = self.timing.phase("resolve_known");
            self.exec("record_seen", 6, vec![])?;
            if self.count("record_seen", 7, vec![])? > 0 {
                self.exec("record_seen", 8, vec![])?;
            }
        }
        Ok(new)
    }

    #[allow(clippy::too_many_arguments)]
    pub fn record_alias(
        &mut self,
        system: &str,
        canonical: &str,
        id64: Option<i64>,
        xyz: [Option<f64>; 3],
        star_class: Option<&str>,
        ts: &str,
    ) -> DbResult<AliasOutcome> {
        if system.is_empty() || canonical.is_empty() || system == canonical {
            return Ok(AliasOutcome::Unchanged);
        }
        self.exec("record_alias", 0, vec![])?;
        if let Some(held) = self.one("record_alias", 1, vec![s(canonical), s(system)])?.and_then(|r| r[0].text()) {
            return Ok(AliasOutcome::HeldBy(held));
        }
        self.exec("record_alias", 2, vec![s(system)])?;
        self.exec(
            "record_alias",
            3,
            vec![
                s(system),
                s(canonical),
                id64.map_or(Value::Null, Value::BigInt),
                opt_f(xyz[0]),
                opt_f(xyz[1]),
                opt_f(xyz[2]),
                opt_s(star_class),
                s(ts),
            ],
        )?;
        Ok(AliasOutcome::Recorded)
    }

    pub fn settled_by(&mut self, names: &[String]) -> DbResult<Vec<Settled>> {
        if names.is_empty() {
            return Ok(Vec::new());
        }
        Ok(self
            .table("settled_by", 0, vec![joined(names)])?
            .into_iter()
            .map(|r| Settled {
                system: r[0].text().unwrap_or_default(),
                sector: r[1].text(),
                is_catalog: r[2].bool(),
                was_classed: r[4].text(),
            })
            .collect())
    }

    pub fn predicted_boxel(&mut self, names: &[String]) -> DbResult<HashSet<String>> {
        if names.is_empty() {
            return Ok(HashSet::new());
        }
        Ok(self.table("predicted_boxel", 0, vec![joined(names)])?.into_iter().filter_map(|r| r[0].text()).collect())
    }

    pub fn solve_route(
        &mut self,
        origin: [f64; 3],
        dest: [f64; 3],
        jump_ly: f64,
        names: (&str, &str),
    ) -> DbResult<Option<Vec<ChainHop>>> {
        if jump_ly <= 0.0 {
            return Ok(None);
        }
        if dist(&origin, &dest) <= jump_ly {
            let c = Corridor::new(Vec::new(), Vec::new(), origin, dest, jump_ly, names.0, names.1, 0);
            return Ok(Some(c.hops(&[])));
        }
        for over in neutron_route::DEFAULT_OVER..=MAX_OVER {
            let direct = dist(&origin, &dest);
            let radius = neutron_route::corridor_radius(direct, jump_ly, over);
            let d = [dest[0] - origin[0], dest[1] - origin[1], dest[2] - origin[2]];
            let len2 = d.iter().map(|v| v * v).sum::<f64>();
            let mut p: Vec<Value> = origin.iter().chain(d.iter()).map(|v| Value::Double(*v)).collect();
            p.push(Value::Double(len2));
            p.push(Value::Double(radius * radius));
            let (sys, pts) = {
                let _p = self.timing.phase("chain_corridor");
                self.named_points("chain_corridor", p)?
            };
            if sys.is_empty() {
                return Ok(None);
            }
            let corridor = Corridor::new(sys, pts, origin, dest, jump_ly, names.0, names.1, over);
            let _p = self.timing.phase("chain_solve");
            if let Some(hops) = corridor.solve() {
                return Ok(Some(hops));
            }
        }
        Ok(None)
    }

    fn named_points(&mut self, name: &str, p: Vec<Value>) -> DbResult<(Vec<String>, Vec<[f64; 3]>)> {
        use duckdb::arrow::array::{Array, AsArray};
        use duckdb::arrow::datatypes::Float64Type;
        let sql = self.stmt(name, 0).to_string();
        let con = self.connection()?;
        let mut stmt = con.prepare(&sql).map_err(|e| e.to_string())?;
        let mut names = Vec::new();
        let mut pts = Vec::new();
        for batch in stmt.query_arrow(params_from_iter(p)).map_err(|e| e.to_string())? {
            let sys = batch.column(0).as_string::<i32>();
            let (x, y, z) = (
                batch.column(1).as_primitive::<Float64Type>(),
                batch.column(2).as_primitive::<Float64Type>(),
                batch.column(3).as_primitive::<Float64Type>(),
            );
            for i in 0..batch.num_rows() {
                if x.is_null(i) || y.is_null(i) || z.is_null(i) {
                    continue;
                }
                names.push(sys.value(i).to_string());
                pts.push([x.value(i), y.value(i), z.value(i)]);
            }
        }
        Ok((names, pts))
    }

    pub fn route_hops(&mut self) -> DbResult<BTreeMap<String, Vec<RouteEnd>>> {
        let mut out: BTreeMap<String, Vec<RouteEnd>> = BTreeMap::new();
        if self.count("route_hops", 0, vec![])? == 0 {
            return Ok(out);
        }
        for r in self.table("route_hops", 1, vec![])? {
            let xyz = match (r[3].float(), r[4].float(), r[5].float()) {
                (Some(x), Some(y), Some(z)) => Some([x, y, z]),
                _ => None,
            };
            out.entry(r[0].text().unwrap_or_default())
                .or_default()
                .push(RouteEnd { system: r[2].text().unwrap_or_default(), xyz });
        }
        Ok(out)
    }

    pub fn carrier_targets(&mut self, pos: Option<[f64; 3]>, limit: i64) -> DbResult<Vec<Row>> {
        if pos.is_none() {
            return Ok(Vec::new());
        }
        let mut p = pos_params(pos);
        p.push(Value::BigInt(limit));
        self.rows("carrier_targets", 0, p)
    }

    pub fn neutron_targets(&mut self, pos: Option<[f64; 3]>, limit: i64) -> DbResult<Vec<Row>> {
        if pos.is_none() {
            return Ok(Vec::new());
        }
        let mut p = pos_params(pos);
        p.push(Value::BigInt(limit));
        p.push(Value::BigInt(limit));
        self.rows("neutron_targets", 0, p)
    }

    pub fn trader_targets(&mut self, pos: Option<[f64; 3]>, per_type: i64) -> DbResult<Vec<Row>> {
        if pos.is_none() {
            return Ok(Vec::new());
        }
        let mut p = pos_params(pos);
        p.push(Value::BigInt(per_type));
        self.rows("trader_targets", 0, p)
    }

    pub fn promote_confirmed(&mut self, only: Option<&[String]>) -> DbResult<i64> {
        let p = match only {
            None => vec![Value::Boolean(true), Value::Text(String::new())],
            Some(names) if names.is_empty() => return Ok(0),
            Some(names) => vec![Value::Boolean(false), joined(names)],
        };
        Ok(self.exec("promote_confirmed", 0, p)? as i64)
    }

    pub fn neutron_corridor(
        &mut self,
        start: [f64; 3],
        dest: [f64; 3],
        pad: f64,
    ) -> DbResult<(Vec<String>, Vec<[f64; 3]>)> {
        let budget = dist(&start, &dest) + pad;
        let mut p: Vec<Value> = start.iter().chain(dest.iter()).map(|v| Value::Double(*v)).collect();
        p.push(Value::Double(budget));
        self.named_points("neutron_corridor", p)
    }

    pub fn counts(&mut self) -> DbResult<BTreeMap<String, i64>> {
        Ok(self
            .table("counts", 0, vec![])?
            .into_iter()
            .filter_map(|r| Some((r[0].text()?, r[1].int()?)))
            .collect())
    }
}

fn query(con: &Connection, sql: &str, params: Vec<Value>) -> DbResult<(Vec<String>, Vec<Vec<Cell>>)> {
    let mut stmt = con.prepare(sql).map_err(|e| e.to_string())?;
    let mut rows = stmt.query(params_from_iter(params)).map_err(|e| e.to_string())?;
    let names: Vec<String> = rows.as_ref().map(|s| s.column_names()).unwrap_or_default();
    let mut out = Vec::new();
    while let Some(row) = rows.next().map_err(|e| e.to_string())? {
        let mut cells = Vec::with_capacity(names.len());
        for i in 0..names.len() {
            cells.push(cell(row.get::<_, Value>(i).map_err(|e| e.to_string())?));
        }
        out.push(cells);
    }
    Ok((names, out))
}

fn sql_path(p: &Path) -> String {
    p.to_string_lossy().replace('\\', "/").replace('\'', "''")
}

fn open(state: &Path, model: &Path, sql: &HashMap<&'static str, Vec<String>>) -> DbResult<Connection> {
    let con = Connection::open_in_memory().map_err(|e| e.to_string())?;
    for stmt in &sql["connect"] {
        con.execute_batch(stmt).map_err(|e| e.to_string())?;
    }
    con.execute_batch(&format!("ATTACH '{}' AS cur", sql_path(state)))
        .map_err(|e| format!("cannot open the app-state database {}: {e}", state.display()))?;
    con.execute_batch(&format!("ATTACH '{}' AS mdl (READ_ONLY)", sql_path(model)))
        .map_err(|e| format!("cannot open the bundled model {}: {e}", model.display()))?;
    con.execute_batch("USE cur").map_err(|e| e.to_string())?;
    con.execute_batch(&sql["record_alias"][0]).map_err(|e| e.to_string())?;
    con.execute_batch(OUTCOME_DDL).map_err(|e| format!("creating system_outcome: {e}"))?;
    con.execute_batch(CARRIER_DESTINATION_DDL).map_err(|e| format!("creating carrier_destination: {e}"))?;
    Ok(con)
}

const STATE_DDL: &[(&str, &str)] = &[
    ("system_seen", include_str!("../../schema/system_seen.sql")),
    ("system_visited", include_str!("../../schema/system_visited.sql")),
    ("system_confirmed", include_str!("../../schema/system_confirmed.sql")),
    ("poi_visited", include_str!("../../schema/poi_visited.sql")),
    ("system_wrong", include_str!("../../schema/system_wrong.sql")),
    ("route", include_str!("../../schema/route.sql")),
    ("system_outcome", OUTCOME_DDL),
    ("carrier_destination", CARRIER_DESTINATION_DDL),
];

pub fn create_state(state: &Path, model: &Path) -> DbResult<usize> {
    let tmp = state.with_extension("creating.duckdb");
    let _ = std::fs::remove_file(&tmp);
    if let Some(dir) = state.parent() {
        std::fs::create_dir_all(dir).map_err(|e| e.to_string())?;
    }
    let sql = rendered_sql();
    let mut seeded = 0;
    {
        let con = Connection::open(&tmp).map_err(|e| e.to_string())?;
        for (_, ddl) in STATE_DDL {
            con.execute_batch(ddl).map_err(|e| e.to_string())?;
        }
        con.execute_batch(&sql["record_alias"][0]).map_err(|e| e.to_string())?;
        con.execute_batch(&format!("ATTACH '{}' AS mdl (READ_ONLY)", sql_path(model)))
            .map_err(|e| e.to_string())?;
        let (_, tables) = query(&con, &sql["seed_state"][0], vec![])?;
        for t in tables.iter().filter_map(|r| r[0].text()) {
            let n = con
                .execute(&format!("INSERT INTO main.{t} BY NAME SELECT * FROM mdl.seed.{t}"), [])
                .map_err(|e| format!("seeding {t}: {e}"))?;
            seeded += n;
        }
        con.execute_batch("DETACH mdl; CHECKPOINT").map_err(|e| e.to_string())?;
    }
    std::fs::rename(&tmp, state).map_err(|e| e.to_string())?;
    Ok(seeded)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn outcome_records_once_and_accumulates_scans() {
        let sql = rendered_sql();
        let con = Connection::open_in_memory().unwrap();
        con.execute_batch(&format!(
            "ATTACH ':memory:' AS mdl; CREATE SCHEMA mdl.model;
             CREATE TABLE {MODEL}.system_predicted (system VARCHAR, system_id BIGINT, sector VARCHAR, is_catalog BOOLEAN,
                 mass_code VARCHAR, {});
             INSERT INTO {MODEL}.system_predicted VALUES ('Eol Prou AB-C d1', NULL, 'Eol Prou', false, 'd', {});
             {OUTCOME_DDL}",
            KINDS.iter().map(|k| format!("{} DOUBLE", k.column)).collect::<Vec<_>>().join(", "),
            vec!["0.25"; KINDS.len()].join(", "),
        ))
        .unwrap();
        let run = |name: &str, params: &[&dyn duckdb::ToSql]| con.execute(&sql[name][0], params).unwrap();
        assert_eq!(run("outcome_visit", &[&"2026-10-21T10:00:00Z", &"Eol Prou AB-C d1"]), 1);
        assert_eq!(run("outcome_visit", &[&"2026-10-22T10:00:00Z", &"Eol Prou AB-C d1"]), 0);
        assert_eq!(run("outcome_visit", &[&"2026-10-22T10:00:00Z", &"Sol"]), 0);
        run("outcome_scan", &[&"Eol Prou AB-C d1", &"Eol Prou AB-C d1 A", &"H"]);
        run("outcome_scan", &[&"Eol Prou AB-C d1", &"Eol Prou AB-C d1 A", &"H"]);
        run("outcome_scan", &[&"Eol Prou AB-C d1", &"Eol Prou AB-C d1 B", &"K"]);
        assert_eq!(run("outcome_complete", &[&"Eol Prou AB-C d1"]), 1);
        assert_eq!(run("outcome_complete", &[&"Eol Prou AB-C d1"]), 0);
        let (bh, wr, stars, complete): (bool, bool, i64, bool) = con
            .query_row(
                "SELECT found_bh, found_wr, len(scanned_stars), all_bodies_found FROM system_outcome",
                [],
                |r| Ok((r.get(0)?, r.get(1)?, r.get(2)?, r.get(3)?)),
            )
            .unwrap();
        assert_eq!((bh, wr, stars, complete), (true, false, 2, true));
        let rows = con.prepare(&sql["outcomes"][0]).unwrap().query_map([], |r| r.get::<_, String>(0)).unwrap().count();
        assert_eq!(rows, 1);
    }

    #[test]
    fn carrier_next_takes_the_reachable_system_closest_to_the_target() {
        let sql = rendered_sql();
        let con = Connection::open_in_memory().unwrap();
        let ddl: String = STATE_DDL.iter().map(|(_, d)| *d).collect::<Vec<_>>().join("
");
        let cols = KINDS.iter().map(|k| format!("{} DOUBLE", k.column)).collect::<Vec<_>>().join(", ");
        con.execute_batch(&format!(
            "ATTACH ':memory:' AS mdl; CREATE SCHEMA mdl.model;
             CREATE TABLE {MODEL}.system_predicted (system VARCHAR, system_id BIGINT, sector VARCHAR, is_catalog BOOLEAN,
                 x DOUBLE, y DOUBLE, z DOUBLE, {cols});
             CREATE TABLE {MODEL}.station (system VARCHAR, is_listed BOOLEAN, is_carrier BOOLEAN, x DOUBLE, y DOUBLE, z DOUBLE);
             {ddl}"
        ))
        .unwrap();
        let rest = vec!["0.0"; KINDS.len()].join(", ");
        for (system, catalog, x) in [("Target", false, 1200.0), ("Near", true, 300.0), ("Far", true, 490.0), ("TooFar", true, 520.0)] {
            con.execute_batch(&format!("INSERT INTO {MODEL}.system_predicted VALUES ('{system}', NULL, 'S', {catalog}, {x}, 0, 0, {rest})"))
                .unwrap();
        }
        con.execute_batch(&format!("INSERT INTO {MODEL}.station VALUES ('Port', true, false, 495, 0, 0), ('Fc', true, true, 499, 0, 0)")).unwrap();
        let next = |target: &str, carrier: f64| -> Option<(f64, Option<String>, Option<f64>)> {
            con.query_row(
                &sql["carrier_next"][0],
                duckdb::params![target, target, target, carrier, 0.0, 0.0, target],
                |r| Ok((r.get(0)?, r.get(3)?, r.get(4)?)),
            )
            .ok()
        };
        let (tx, system, jump) = next("Target", 0.0).unwrap();
        assert_eq!(tx, 1200.0);
        assert_eq!(system.as_deref(), Some("Port"));
        assert!((jump.unwrap() - 495.0).abs() < 1e-9);
        let (_, system, _) = next("Target", 900.0).unwrap();
        assert_eq!(system.as_deref(), Some("Target"));
        assert!(next("Unknown", 0.0).is_none());
    }

    #[test]
    fn sector_best_picks_the_likeliest_unsettled_system() {
        let sql = rendered_sql();
        let con = Connection::open_in_memory().unwrap();
        let ddl: String = STATE_DDL.iter().map(|(_, d)| *d).collect::<Vec<_>>().join("
");
        con.execute_batch(&format!(
            "ATTACH ':memory:' AS mdl; CREATE SCHEMA mdl.model;
             CREATE TABLE {MODEL}.system_predicted (system VARCHAR, system_id BIGINT, sector VARCHAR, is_catalog BOOLEAN, {},
                 mass_code VARCHAR, x DOUBLE, y DOUBLE, z DOUBLE);
             {ddl}
             {}",
            KINDS.iter().map(|k| format!("{} DOUBLE", k.column)).collect::<Vec<_>>().join(", "),
            sql["record_alias"][0],
        ))
        .unwrap();
        let rest = vec!["0.0"; KINDS.len() - 1].join(", ");
        for (system, sector, catalog, p) in [
            ("Eol Prou AA-A h1", "Eol Prou", false, "0.40"),
            ("Eol Prou AA-A h2", "Eol Prou", false, "0.90"),
            ("Eol Prou AA-A h3", "Eol Prou", false, "0.95"),
            ("Eol Prou AA-A h4", "Eol Prou", true, "0.99"),
            ("Eol Prou AA-A h5", "Eol Prou", false, "0.97"),
        ] {
            con.execute_batch(&format!(
                "INSERT INTO {MODEL}.system_predicted VALUES ('{system}', NULL, '{sector}', {catalog}, {p}, {rest}, NULL, NULL, NULL, NULL)"
            ))
            .unwrap();
        }
        con.execute_batch(
            "INSERT INTO system_visited (system, first_visited_utc) VALUES ('Eol Prou AA-A h3', now());
             INSERT INTO system_wrong (system, marked_utc) VALUES ('Eol Prou AA-A h5', now());",
        )
        .unwrap();
        let column = KINDS[0].column;
        let pick = |catalogued: bool, sector: &str| -> Option<String> {
            con.query_row(&sql["sector_best"][0], duckdb::params![column, sector, catalogued], |r| r.get(0)).ok()
        };
        assert_eq!(pick(false, "Eol Prou").as_deref(), Some("Eol Prou AA-A h2"));
        assert_eq!(pick(true, "Eol Prou").as_deref(), Some("Eol Prou AA-A h4"));
        assert_eq!(pick(false, "Nowhere"), None);
    }

    fn boxel_id64_of(con: &Connection, system: &str, mass_code: &str, xyz: [f64; 3]) -> Option<i64> {
        let boxel = SQL.iter().find(|(n, _)| *n == "boxel_id64").unwrap().1;
        con.query_row(
            &format!(
                "SELECT {boxel} FROM (SELECT ?::VARCHAR AS system, NULL::BIGINT AS system_id, ?::VARCHAR AS mass_code,
                 ?::DOUBLE AS x, ?::DOUBLE AS y, ?::DOUBLE AS z) p"
            ),
            duckdb::params![system, mass_code, xyz[0], xyz[1], xyz[2]],
            |r| r.get(0),
        )
        .unwrap()
    }

    #[test]
    fn boxel_prediction_derives_the_id64_the_game_reports() {
        let con = Connection::open_in_memory().unwrap();
        for (system, xyz, id64) in [
            ("Col 359 Sector IH-V e2-13", [-617.2642, 50.39773, 613.79261], 57128518868),
            ("Dumbbell Sector BA-A e5", [-943.20313, -41.17188, 483.80469], 22760383692),
            ("B133 Sector CL-Y e10", [-558.53125, -146.6875, 878.41667], 44243608804),
        ] {
            assert_eq!(boxel_id64_of(&con, system, "e", xyz), Some(id64), "{system}");
        }
        assert_eq!(boxel_id64_of(&con, "Sol", "e", [0.0; 3]), None);
    }

    #[test]
    fn route_to_a_renamed_prediction_settles_it() {
        let sql = rendered_sql();
        let con = Connection::open_in_memory().unwrap();
        let ddl: String = STATE_DDL.iter().map(|(_, d)| *d).collect::<Vec<_>>().join("\n");
        let zeros = vec!["0.0"; KINDS.len() - 1].join(", ");
        con.execute_batch(&format!(
            "ATTACH ':memory:' AS mdl; CREATE SCHEMA mdl.model;
             CREATE TABLE {MODEL}.system_predicted (system VARCHAR, system_id BIGINT, sector VARCHAR, is_catalog BOOLEAN, {},
                 mass_code VARCHAR, x DOUBLE, y DOUBLE, z DOUBLE);
             INSERT INTO {MODEL}.system_predicted VALUES
                 ('Col 359 Sector IH-V e2-13', NULL, 'Col 359 Sector', false, 0.5, {zeros}, 'e', -617.2642, 50.39773, 613.79261),
                 ('Col 359 Sector IH-V e2-14', NULL, 'Col 359 Sector', false, 0.4, {zeros}, 'e', -617.2642, 50.39773, 613.79261);
             {ddl}
             {}",
            KINDS.iter().map(|k| format!("{} DOUBLE", k.column)).collect::<Vec<_>>().join(", "),
            sql["record_alias"][0],
        ))
        .unwrap();
        let summary = || -> [i64; 4] {
            con.query_row(&sql["sector_summary"][0], ["Col 359 Sector"], |r| {
                Ok([r.get(0)?, r.get(1)?, r.get(2)?, r.get(3)?])
            })
            .unwrap()
        };
        let best = || -> Option<String> {
            con.query_row(&sql["sector_best"][0], duckdb::params![KINDS[0].column, "Col 359 Sector", false], |r| r.get(0))
                .ok()
        };
        assert_eq!(summary(), [2, 0, 0, 0]);
        assert_eq!(best().as_deref(), Some("Col 359 Sector IH-V e2-13"));
        let seen = &sql["record_seen"];
        con.execute_batch(&seen[0]).unwrap();
        con.execute(
            &seen[1],
            duckdb::params!["Stock 1 Sector HW-W e1-13", "A", -702.8125, 19.15625, 561.03125, 57128518868i64],
        )
        .unwrap();
        for stmt in &seen[2..4] {
            con.execute_batch(stmt).unwrap();
        }
        con.execute(&seen[5], ["2026-10-24T11:13:20+00:00"]).unwrap();
        assert_eq!(summary(), [2, 0, 1, 0]);
        assert_eq!(best().as_deref(), Some("Col 359 Sector IH-V e2-14"));
    }
}
