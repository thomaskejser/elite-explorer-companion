SELECT count(*) FILTER (WHERE eligible),
       count(*) FILTER (WHERE eligible AND visited),
       count(*) FILTER (WHERE eligible AND NOT visited AND settled),
       count(*) FILTER (WHERE p.is_catalog)
FROM (
  SELECT p.is_catalog,
         NOT p.is_catalog AND greatest({{RARE_MAX}}) >= {{MIN_RARE}} AS eligible,
         v.system IS NOT NULL AS visited,
         {{SEEN_CLASS}} IS NOT NULL AS settled
  FROM {{MODEL}}.system_predicted p
  {{SEEN_JOIN}}
  WHERE p.sector = ? AND {{UNGATED}}
) p
