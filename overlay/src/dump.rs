use std::path::Path;

use serde_json::{Value, json};

use crate::args::Args;
use crate::database::Database;
use crate::kinds::KINDS;
use crate::row::Row;
use crate::table::{cell_colour, cell_text};
use crate::theme::{self, Column};
use crate::timing::Phases;
use crate::{app, route};

fn row_json(r: &Row) -> Value {
    let mut m = serde_json::Map::new();
    m.insert("rank".into(), json!(r.rank));
    m.insert("n".into(), json!(r.n));
    m.insert("system".into(), json!(r.system));
    m.insert("type_label".into(), json!(r.type_label));
    m.insert("dist_ly".into(), json!(r.dist_ly));
    m.insert("dist_approx".into(), json!(r.dist_approx));
    for (k, v) in KINDS.iter().zip(r.p) {
        m.insert(k.column.into(), json!(v));
    }
    m.insert("row_grp".into(), json!(r.row_grp));
    m.insert("wide_text".into(), json!(r.wide_text));
    m.insert("detail".into(), json!(r.detail));
    m.insert("mass_code".into(), json!(r.mass_code));
    m.insert("boxel".into(), json!(r.boxel));
    m.insert("x".into(), json!(r.x));
    m.insert("y".into(), json!(r.y));
    m.insert("z".into(), json!(r.z));
    m.insert("dist_sol".into(), json!(r.dist_sol));
    m.insert("star_class".into(), json!(r.star_class));
    m.insert("copy_text".into(), json!(r.copy_text));
    m.insert("candidates".into(), json!(r.candidates));
    m.insert("kind_count".into(), json!(r.kind_count));
    Value::Object(m)
}

fn rendered(rows: &[Row], columns: &[Column]) -> Value {
    Value::Array(
        rows.iter()
            .map(|r| {
                Value::Array(
                    columns.iter().map(|c| json!([cell_text(r, c, false), cell_colour(r, c).to_hex()])).collect(),
                )
            })
            .collect(),
    )
}

pub fn run(args: &Args, state: &Path, model: &Path) -> Result<(), String> {
    let timing = Phases::new(0, "");
    let mut db = Database::new(state, model, timing.clone());
    let pos = args.pos.as_ref().map(|p| [p[0], p[1], p[2]]);
    let sector = args.sector.clone();
    let mut out = serde_json::Map::new();
    let mut put = |name: &str, rows: &[Row], columns: &[Column]| {
        out.insert(name.into(), json!({"rows": rows.iter().map(row_json).collect::<Vec<_>>(),
                                       "cells": rendered(rows, columns)}));
    };
    put("confirmed_targets", &db.confirmed_targets(pos)?, &theme::confirmed_columns());
    put("carrier_targets", &db.carrier_targets(pos, 1)?, &theme::nearest_columns());
    put("neutron_targets", &db.neutron_targets(pos, 1)?, &theme::nearest_columns());
    put("adjacent_sectors", &db.adjacent_sectors(sector.as_deref(), pos, app::ROWS as i64)?, &theme::columns());
    if let Some(s) = &sector {
        put("top_targets", &db.top_targets(s, app::ROWS as i64, pos)?, &theme::columns());
        put("unfound_targets", &db.unfound_targets(s, app::UNFOUND_ROWS, pos)?, &theme::columns());
        put("sector_totals", &db.sector_totals(s)?, &theme::columns());
        put("region_totals", &db.region_totals(s, pos)?.unwrap_or_default(), &theme::columns());
        out.insert("sector_summary".into(), json!(db.sector_summary(s)?));
    }
    if let (Some(p), Some(to)) = (pos, args.chain_to.as_ref()) {
        let to = [to[0], to[1], to[2]];
        let t0 = std::time::Instant::now();
        let chain = {
            let _span = timing.span("solve_route");
            db.solve_route(p, to, args.range, ("(start)", "(goal)"))?
        };
        let chain_secs = t0.elapsed().as_secs_f64();
        out.insert(
            "solve_route".into(),
            json!({"hops": chain.map(|h| h.into_iter().map(|h| h.system).collect::<Vec<_>>()), "secs": chain_secs}),
        );
        let t0 = std::time::Instant::now();
        let (names, xyz) = db.neutron_corridor(p, to, 600.0)?;
        let plan = route::plan(&xyz, &p, &to, args.plain_range, args.range);
        out.insert(
            "plan".into(),
            json!({"corridor": names.len(),
                   "hops": plan.map(|h| h.into_iter().map(|i| names[i].clone()).collect::<Vec<_>>()),
                   "secs": t0.elapsed().as_secs_f64()}),
        );
    }
    out.insert("foreground".into(), json!(crate::win::focus::is_foreground()));
    out.insert("throttle_present".into(), json!(crate::lights::Lights::new(true).present()));
    println!("{}", Value::Object(out));
    Ok(())
}
