import sys, pathlib, importlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent))
from common.db import connect

stage = importlib.import_module("etl.station.stage")
load = importlib.import_module("etl.station.load")


def main():
    path = stage.fetch()
    con = connect(memory_limit="8GB", threads=8)
    try:
        stage.stage(con, path)
        load.load(con)
    finally:
        con.close()
    print("DONE_REFRESH_STATION")


if __name__ == "__main__":
    from common.runlog import start
    start()
    main()
