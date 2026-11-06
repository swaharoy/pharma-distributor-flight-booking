"""The scripted cases under tests/cases/, replayed offline through the real tools and the real verifier:
each gets the verdict it expects, and each keeps to the hosted budget and the prescribed path."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from replay import matches, replay

CASES = sorted((Path(__file__).resolve().parent / "cases").glob("*.json"))


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_there_are_gold_wrong_missing_malformed_tampered_and_boundary_cases() -> None:
    kinds = {load(path)["kind"] for path in CASES}
    assert kinds == {"gold", "wrong", "missing", "malformed", "tampered", "boundary"}
    assert sum(load(path)["kind"] == "gold" for path in CASES) >= 8


@pytest.mark.parametrize("path", CASES, ids=[path.stem for path in CASES])
def test_each_case_gets_its_verdict(path: Path) -> None:
    case = load(path)
    problems = matches(replay(case), case["expect"])
    assert not problems, problems


@pytest.mark.parametrize("path", CASES, ids=[path.stem for path in CASES])
def test_each_case_keeps_to_the_hosted_budget(path: Path) -> None:
    case = load(path)
    tools = [step["tool"] for step in case["steps"] if "tool" in step] + ["submit"]
    assert len(tools) <= 5, "the hosted agent has six steps"
    if case["kind"] == "gold":
        unapproved = case["expect"]["valid"] and case["steps"][-1]["submit"]["refusal"] == "NO_SVP_APPROVAL"
        assert tools == (["get_trip", "submit"] if unapproved else ["get_trip", "search_flights", "submit"])
