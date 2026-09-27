import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent))
from common.db import connect
from common.codex import stage_codex_feeds


def stage(con):
    stage_codex_feeds(con)


def main():
    con = connect()
    try:
        stage(con)
    finally:
        con.close()
    print("DONE_STAGE_SYSTEM_PHENOMENON")


if __name__ == "__main__":
    main()
