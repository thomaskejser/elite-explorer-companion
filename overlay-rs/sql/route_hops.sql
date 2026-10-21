SELECT count(*) FROM duckdb_tables()
WHERE database_name = 'cur' AND schema_name = 'main' AND table_name = 'route';
SELECT route, hop, system, x, y, z FROM main.route ORDER BY route, hop;
