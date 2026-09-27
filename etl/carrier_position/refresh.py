import sys, pathlib, importlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent))
from common.db import connect

load = importlib.import_module("etl.carrier_position.load")


def main():
    con = connect()
    try:
        load.load(con)
    finally:
        con.close()
    print("DONE_REFRESH_CARRIER_POSITION")


if __name__ == "__main__":
    main()
