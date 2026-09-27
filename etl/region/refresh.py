import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent))
from common.db import connect

import importlib
stage = importlib.import_module("etl.region.stage")
load = importlib.import_module("etl.region.load")


def main():
    con = connect()
    try:
        stage.stage(con)
        load.load(con)
    finally:
        con.close()
    print("DONE_REFRESH_REGION")


if __name__ == "__main__":
    main()
