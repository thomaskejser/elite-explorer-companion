CREATE OR REPLACE TABLE staging.sys_value AS
SELECT sb.system_id, count(*) AS n_bodies, sum(
  CASE WHEN b.value_formula = 'star'
       THEN coalesce(b.cr_value, 0)
            + coalesce(sb.solar_masses, 0) * coalesce(b.cr_value, 0) / 66.25
       ELSE greatest(
              coalesce(CASE WHEN sb.is_terraformable
                            THEN coalesce(b.cr_value_terraformable, b.cr_value)
                            ELSE b.cr_value END, b.cr_value)
              * (1 + pow(coalesce(sb.earth_masses, 0), 0.2) * 0.56591828), 500)
  END) AS base_cr
FROM main.system_body sb
JOIN main.body b ON b.body_id = sb.body_id
GROUP BY 1;

COMMENT ON TABLE staging.sys_value IS
'WORK TABLE, safe to drop: the scan value of every system that has body rows, summed from main.system_body JOIN main.body. It costs a pass over all 570M system_body rows, so etl/system_predicted/load.py REUSES it across runs and recomputes only on --refresh-value, or when none of a 2,000-row sample of its system_id resolves in main.system_known.

*** A REUSED COPY IS AS OLD AS ITS LAST --refresh-value. *** It feeds only the per-mass-code averages in transform.pred_value, so staleness moves exp_scan_value_cr slowly; it is never a per-system fact to quote.';

COMMENT ON COLUMN staging.sys_value.system_id IS
'main.system_known.system_id (the game''s id64). One row per system with at least one typed body row.';

COMMENT ON COLUMN staging.sys_value.n_bodies IS
'Body rows with a known body type in main.system_body. A count of REPORTED bodies, a lower bound on what the system holds.';

COMMENT ON COLUMN staging.sys_value.base_cr IS
'Estimated credits for scanning the reported bodies: stars by the cr_value mass formula, planets by the terraformable-aware formula floored at 500. An ESTIMATE over reported bodies only, NOT the in-game payout and not a full-system value.';
