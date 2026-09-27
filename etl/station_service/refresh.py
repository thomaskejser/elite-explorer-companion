import sys, pathlib, importlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent))
from common.db import connect

stage = importlib.import_module("etl.station_service.stage")
load = importlib.import_module("etl.station_service.load")


def main():
    path = stage.fetch()
    con = connect()
    try:
        stage.stage(con, path)
        load.load(con)
    finally:
        con.close()
    print("DONE_REFRESH_STATION_SERVICE")


if __name__ == "__main__":
    main()
