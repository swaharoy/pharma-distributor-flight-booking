"""Helpers shared by the verifier modules. Pure functions of their arguments and the files on disk."""

import json
import re
from pathlib import Path

RUN_ID = re.compile(r"^[0-9a-f]{12}$")


def result(valid, message, *, score=None, **details):
    return {
        "valid": valid,
        "score": float(valid) if score is None else score,
        "message": message,
        "details": details,
    }


def check(check_id, constraint, ok, expected="", actual="", message=""):
    """One named constraint of a verdict: ok is True, False, or None when it was not checked."""
    return {
        "id": check_id,
        "constraint": constraint,
        "ok": ok,
        "expected": expected,
        "actual": actual,
        "message": message,
    }


def read_json(path):
    """A receipt's JSON, or None when the file is missing or not JSON."""
    path = Path(path)
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        return None


def run_files(workspace, run_id):
    """(trip receipt, [search receipts in call order]) of a run, or (None, []) when it has none."""
    if not RUN_ID.fullmatch(run_id):
        return None, []
    folder = Path(workspace) / "runs" / run_id
    trip = read_json(folder / "trip.json")
    searches = []
    if folder.is_dir():
        paths = [path for path in folder.iterdir() if re.fullmatch(r"search-\d+\.json", path.name)]
        for path in sorted(paths, key=lambda item: int(item.name[7:-5])):
            searches.append(read_json(path))
    return trip, searches
