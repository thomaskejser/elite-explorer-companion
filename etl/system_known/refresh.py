import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent))
from common.db import connect

import importlib
stage = importlib.import_module("etl.system_known.stage")
load = importlib.import_module("etl.system_known.load")


def _arg(flag, default=None):
    return sys.argv[sys.argv.index(flag) + 1] if flag in sys.argv else default


def main():
    window = _arg("--window")
    if window and window not in stage.WINDOWS:
        raise SystemExit(f"--window must be one of {', '.join(stage.WINDOWS)}")
    only = _arg("--only")
    con = connect(memory_limit="4GB", threads=8)
    try:
        stage.stage(con, window, only.split(",") if only else None, "--force" in sys.argv)
        load.load(con)
    finally:
        con.close()
    print("DONE_REFRESH_SYSTEM_KNOWN")


if __name__ == "__main__":
    main()
