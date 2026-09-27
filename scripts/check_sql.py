import pathlib
import sys

import duckdb

ROOT = pathlib.Path(__file__).resolve().parent.parent
PLACEHOLDERS = {"${table}": "placeholder_table", "${provenance}": "p", "${url}": "u"}


def main():
    con = duckdb.connect(":memory:")
    files = sorted(ROOT.glob("schema/**/*.sql")) + sorted(ROOT.glob("etl/**/*.sql"))
    bad = 0
    for path in files:
        text = path.read_text(encoding="utf-8")
        for k, v in PLACEHOLDERS.items():
            text = text.replace(k, v)
        try:
            con.extract_statements(text)
        except Exception as exc:                                       # noqa: BLE001
            bad += 1
            print(f"{path.relative_to(ROOT)}: {str(exc).splitlines()[0]}")
    print(f"\n{len(files)} file(s) checked, {bad} failed to parse")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
