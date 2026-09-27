import sys, pathlib, importlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent))
from common.db import connect

load = importlib.import_module("etl.system_poi.load")


def main():
    con = connect()
    try:
        load.load(con)
    finally:
        con.close()
    print("DONE_REFRESH_SYSTEM_POI")


if __name__ == "__main__":
    main()
