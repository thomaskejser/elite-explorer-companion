import sys, pathlib, importlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent))
from common.db import connect

stage = importlib.import_module("etl.system_phenomenon.stage")
load = importlib.import_module("etl.system_phenomenon.load")


def main():
    con = connect(memory_limit="8GB")
    try:
        stage.stage(con)
        load.load(con)
    finally:
        con.close()
    print("DONE_REFRESH_SYSTEM_PHENOMENON")


if __name__ == "__main__":
    main()
