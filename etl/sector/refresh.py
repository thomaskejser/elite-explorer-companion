import sys, pathlib, importlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent))
from common.db import connect

stage = importlib.import_module("etl.sector.stage")
load = importlib.import_module("etl.sector.load")


def main():
    con = connect()
    try:
        stage.stage(con)
        load.load(con)
    finally:
        con.close()
    print("DONE_REFRESH_SECTOR")


if __name__ == "__main__":
    main()
