SELECT ordinal_position, column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_schema = %(schema)s AND table_name = %(view)s
ORDER BY ordinal_position
