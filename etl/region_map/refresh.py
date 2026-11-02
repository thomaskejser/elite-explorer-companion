import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent))
from common.db import connect

import importlib
stage = importlib.import_module("etl.region_map.stage")
load = importlib.import_module("etl.region_map.load")


def main():
    con = connect()
    try:
        stage.stage(con)
        load.load(con)
    finally:
        con.close()
    print("DONE_REFRESH_REGION_MAP")


if __name__ == "__main__":
    from common.runlog import start
    start()
    main()
