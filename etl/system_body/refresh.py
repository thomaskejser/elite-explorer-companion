import sys, pathlib, importlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent))
from common.db import connect

stage = importlib.import_module("etl.system_body.stage")
load = importlib.import_module("etl.system_body.load")


def _arg(flag, default=None):
    return sys.argv[sys.argv.index(flag) + 1] if flag in sys.argv else default


def main():
    window = _arg("--window")
    buckets = _arg("--buckets")
    limit = _arg("--limit")
    con = connect(memory_limit="6GB", threads=8)
    try:
        stage.stage(con, window, "--force" in sys.argv)
        load.load(con, int(buckets) if buckets else None, int(limit) if limit else None)
    finally:
        con.close()
    print("DONE_REFRESH_SYSTEM_BODY")


if __name__ == "__main__":
    main()
