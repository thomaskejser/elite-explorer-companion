MERGE INTO main.system_exobio AS t
USING transform.system_exobio AS s ON t.system_id = s.system_id
WHEN MATCHED AND (t.system           IS DISTINCT FROM s.system
               OR t.x                IS DISTINCT FROM s.x
               OR t.y                IS DISTINCT FROM s.y
               OR t.z                IS DISTINCT FROM s.z
               OR t.candidate_bodies IS DISTINCT FROM s.candidate_bodies
               OR t.unmapped_bodies  IS DISTINCT FROM s.unmapped_bodies
               OR t.worked_bodies    IS DISTINCT FROM s.worked_bodies
               OR t.cr_expected      IS DISTINCT FROM s.cr_expected
               OR t.best_body        IS DISTINCT FROM s.best_body
               OR t.best_cr          IS DISTINCT FROM s.best_cr
               OR t.best_species     IS DISTINCT FROM s.best_species
               OR t.last_reported    IS DISTINCT FROM s.last_reported)
THEN UPDATE SET system           = s.system,
                x                = s.x,
                y                = s.y,
                z                = s.z,
                candidate_bodies = s.candidate_bodies,
                unmapped_bodies  = s.unmapped_bodies,
                worked_bodies    = s.worked_bodies,
                cr_expected      = s.cr_expected,
                best_body        = s.best_body,
                best_cr          = s.best_cr,
                best_species     = s.best_species,
                last_reported    = s.last_reported
WHEN NOT MATCHED THEN INSERT
    (system_id, system, x, y, z, candidate_bodies, unmapped_bodies, worked_bodies, cr_expected, best_body, best_cr, best_species, last_reported)
VALUES
    (s.system_id, s.system, s.x, s.y, s.z, s.candidate_bodies, s.unmapped_bodies, s.worked_bodies, s.cr_expected, s.best_body, s.best_cr, s.best_species, s.last_reported);
