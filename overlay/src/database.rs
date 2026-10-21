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
const MAX_POI_ROWS: &str = "3";
pub const SECTOR_CANDIDATES: usize = 10;
const MAX_OVER: u32 = 4;
const CATALOGUED_LABEL: &str = "  + CATALOGUED";
const LIST_SEP: char = '\u{1f}';

macro_rules! sql_files {
    ($($name:literal),* $(,)?) => {
        &[$(($name, include_str!(concat!("../sql/", $name, ".sql")))),*]
    };
}

const SQL: &[(&str, &str)] = sql_files!(
    "confirmed_cte",
    "confirmed_targets",
    "top_targets",
    "unfound_targets",
    "adjacent_sectors",
    "sector_totals",
    "region_totals",
    "region_expected",
    "sector_expected",
    "trade_targets",
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

pub const WRITES: [&str; 6] =
    ["record_arrival", "record_seen", "record_poi_visit", "mark_wrong", "promote_confirmed", "record_alias"];

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
        "P_ORDER",
        format!(
            "CASE ? {} END",
            cols.iter().map(|c| format!("WHEN '{c}' THEN sum(p.{c})")).collect::<Vec<_>>().join(" ")
        ),
    );
    f.insert("P_SUMS_BARE", cols.iter().map(|c| format!("sum({c}) AS {c}")).collect::<Vec<_>>().join(", "));
    f.insert("SEEN_CLASS", "coalesce(s.star_class, si.star_class, sa.star_class)".to_string());
    f.insert(
        "SEEN_JOIN",
        "LEFT JOIN system_seen s ON s.system = p.system \
         LEFT JOIN system_seen si ON si.system_id = p.system_id \
         LEFT JOIN system_alias al ON al.system = p.system \
         LEFT JOIN system_seen sa ON sa.system = al.canonical"
            .to_string(),
    );
    f.insert("MIN_RARE", MIN_RARE.to_string());
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
pub struct TradeRow {
    pub kind: String,
    pub system: String,
    pub station: String,
    pub dist_ly: Option<f64>,
    pub arrival_ls: Option<f64>,
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

    fn totals_pair(&mut self, label: &str, name: &str, sector: &str) -> DbResult<Vec<Row>> {
        let table = self.table(name, 0, vec![s(sector)])?;
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
        self.totals_pair(&format!("SECTOR {sector}"), "sector_totals", sector)
    }

    pub fn region_totals(&mut self, sector: &str) -> DbResult<Option<Vec<Row>>> {
        let Some(region) = self.one("region_of", 0, vec![s(sector)])?.and_then(|r| r[0].text()) else {
            return Ok(None);
        };
        self.totals_pair(&format!("REGION {region}"), "region_totals", sector).map(Some)
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

    pub fn region_expected(&mut self) -> DbResult<Vec<RegionExpected>> {
        let _p = self.timing.phase("region_expected");
        Ok(Self::expected_rows(self.table("region_expected", 0, Vec::new())?))
    }

    pub fn sector_expected(&mut self, region_id: i64, column: &str, limit: i64) -> DbResult<Vec<RegionExpected>> {
        let _p = self.timing.phase("sector_expected");
        let params = vec![Value::BigInt(region_id), s(column), Value::BigInt(limit)];
        Ok(Self::expected_rows(self.table("sector_expected", 0, params)?))
    }

    pub fn trade_targets(&mut self, pos: [f64; 3]) -> DbResult<Vec<TradeRow>> {
        let params = pos.iter().map(|&v| Value::Double(v)).collect();
        Ok(self
            .table("trade_targets", 0, params)?
            .into_iter()
            .map(|r| TradeRow {
                kind: r[0].text().unwrap_or_default(),
                system: r[1].text().unwrap_or_default(),
                station: r[2].text().unwrap_or_default(),
                dist_ly: r[3].float(),
                arrival_ls: r[4].float(),
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
    Ok(con)
}

const STATE_DDL: &[(&str, &str)] = &[
    ("system_seen", include_str!("../../schema/system_seen.sql")),
    ("system_visited", include_str!("../../schema/system_visited.sql")),
    ("system_confirmed", include_str!("../../schema/system_confirmed.sql")),
    ("poi_visited", include_str!("../../schema/poi_visited.sql")),
    ("system_wrong", include_str!("../../schema/system_wrong.sql")),
    ("route", include_str!("../../schema/route.sql")),
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
