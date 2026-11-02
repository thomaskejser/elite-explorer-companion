import sys, pathlib, importlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent))
from common.db import connect

stage = importlib.import_module("etl.codex_sighting.stage")
load = importlib.import_module("etl.codex_sighting.load")


def main():
    con = connect(memory_limit="8GB")
    try:
        stage.stage(con)
        load.load(con)
    finally:
        con.close()
    print("DONE_REFRESH_CODEX_SIGHTING")


if __name__ == "__main__":
    from common.runlog import start
    start()
    main()
