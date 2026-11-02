import sys, pathlib, importlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent))
from common.db import connect

load = importlib.import_module("etl.exobio_odds.load")


def main():
    con = connect(memory_limit="10GB")
    try:
        load.load(con)
    finally:
        con.close()
    print("DONE_REFRESH_EXOBIO_ODDS")


if __name__ == "__main__":
    from common.runlog import start
    start()
    main()
