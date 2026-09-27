import sys, pathlib, importlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent))
from common.db import connect

load = importlib.import_module("etl.system_predicted.load")


def main():
    con = connect(memory_limit="8GB", threads=8)
    try:
        load.load(con, "--refresh-value" in sys.argv)
    finally:
        con.close()
    print("DONE_REFRESH_SYSTEM_PREDICTED")


if __name__ == "__main__":
    main()
