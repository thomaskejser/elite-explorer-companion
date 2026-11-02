SELECT o.table_name,
       EXISTS (SELECT 1 FROM duckdb_tables() n
               WHERE n.database_name = current_database() AND n.schema_name = 'main'
                 AND n.table_name = o.table_name) AS present
FROM duckdb_tables() o
WHERE o.database_name = 'old' AND o.schema_name = 'main'
ORDER BY o.table_name;
