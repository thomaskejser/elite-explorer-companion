UPDATE system_outcome SET all_bodies_found = TRUE, updated_utc = now() WHERE system = ? AND NOT all_bodies_found
