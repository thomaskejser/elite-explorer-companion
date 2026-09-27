CREATE OR REPLACE MACRO clean_sector_name(s) AS (
    CASE WHEN s IS NULL THEN NULL ELSE nullif(
        array_to_string(
            list_transform(
                string_split(trim(regexp_replace(s, '\s+', ' ', 'g')), ' '),
                w -> CASE
                        WHEN w IN ('of', 'and', 'the') THEN w
                        WHEN upper(w) IN ('NGC', 'IC', 'ICZ', 'LBN') THEN upper(w)
                        WHEN length(w) > 1 AND regexp_matches(w, '^[a-z]+(-[a-z]+)*$')
                            THEN array_to_string(
                                     list_transform(string_split(w, '-'),
                                         p -> upper(p[1]) || p[2:]),
                                     '-')
                        ELSE w
                     END),
            ' '), '')
    END
);
