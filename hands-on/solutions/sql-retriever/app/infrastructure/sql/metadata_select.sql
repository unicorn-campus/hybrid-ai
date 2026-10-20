SELECT key, value
FROM public.lab_metadata
WHERE key IN ('base_date', 'txn_period')
