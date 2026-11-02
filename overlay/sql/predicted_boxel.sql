SELECT system FROM {{MODEL}}.system_predicted
WHERE system IN (SELECT unnest(string_split(?, chr(31)))) AND is_catalog = FALSE
