import os
import sys


def log(msg: str):
    if os.environ.get("NIDUS_DEBUG") == "1":
        print(f"[Nidus] {msg}", flush=True, file=sys.stderr)
