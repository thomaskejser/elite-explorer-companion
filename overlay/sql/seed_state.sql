SELECT table_name FROM duckdb_tables()
WHERE database_name = 'mdl' AND schema_name = 'seed';
