SELECT column_name FROM duckdb_columns()
WHERE database_name = ? AND schema_name = 'main' AND table_name = ?
ORDER BY column_index;
