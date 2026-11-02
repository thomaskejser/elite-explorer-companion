import sys, pathlib, importlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent))
from common.db import connect

load = importlib.import_module("etl.prediction_outcome.load")


def main():
    con = connect(memory_limit="8GB", threads=8)
    try:
        load.load(con)
    finally:
        con.close()
    print("DONE_REFRESH_PREDICTION_OUTCOME")


if __name__ == "__main__":
    from common.runlog import start
    start()
    main()
