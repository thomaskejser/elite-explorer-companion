import sys, pathlib, importlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent))
from common.db import connect

stage = importlib.import_module("etl.system_catalog.stage")
load = importlib.import_module("etl.system_catalog.load")


def main():
    con = connect()
    try:
        stage.stage(con)
        load.load(con)
    finally:
        con.close()
    print("DONE_REFRESH_SYSTEM_CATALOG")


if __name__ == "__main__":
    main()
