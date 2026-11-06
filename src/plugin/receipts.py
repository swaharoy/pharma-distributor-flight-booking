"""Receipts: what each tool call did, written to the workspace so the verifier can check a submission
against them. Each run of the booking task (one get_trip call) gets its own folder, runs/<run id>/."""

import json
import re
import secrets
from datetime import UTC, datetime
from pathlib import Path

RUNS = "runs"
RUN_ID = re.compile(r"^[0-9a-f]{12}$")


def now() -> str:
    """The current UTC time, YYYY-MM-DD HH:MM:SS.ffffff (tests replace this clock)."""
    return datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S.%f")


CLOCK = now


def new_run(workspace: Path, request: dict, booking_date: str, started_at: str) -> str:
    """A new run folder holding trip.json: the request, its booking date and when the run began. Returns its id."""
    run_id = secrets.token_hex(6)
    folder = workspace / RUNS / run_id
    folder.mkdir(parents=True, exist_ok=False)
    write(folder / "trip.json", {"run_id": run_id, "request": request, "booking_date": booking_date,
                                 "started_at": started_at})
    return run_id


def run_trip(workspace: Path, run_id: str) -> tuple[Path, dict]:
    """The folder and trip.json of a run get_trip began; raises when there is none."""
    if not RUN_ID.fullmatch(run_id):
        raise ValueError(f"run_id {run_id!r} is not one get_trip returned")
    folder = workspace / RUNS / run_id
    path = folder / "trip.json"
    if not path.is_file():
        raise ValueError(f"no run {run_id}: call get_trip first and pass the run_id it returns")
    return folder, json.loads(path.read_text(encoding="utf-8"))


def add_search(folder: Path, receipt: dict) -> None:
    """search-<n>.json, numbered in call order."""
    number = len(list(folder.glob("search-*.json"))) + 1
    write(folder / f"search-{number}.json", receipt)


def write(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=1, sort_keys=True) + "\n", encoding="utf-8")
