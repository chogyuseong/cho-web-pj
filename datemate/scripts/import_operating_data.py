"""Import operator-reviewed source facts into a NEW local evidence file."""

import argparse, json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import store
from app.catalog import places
from app.operating_import import import_file
from app.restaurants import restaurants

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input")
    parser.add_argument("new_output")
    args = parser.parse_args()
    store.init()
    print(
        json.dumps(
            import_file(
                args.input, args.new_output, {p["id"] for p in places("real") + restaurants()}
            ),
            ensure_ascii=False,
        )
    )
