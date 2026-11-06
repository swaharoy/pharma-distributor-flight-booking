"""Replay a scripted case offline, as NanoAgent runs the booking task: the answer key pinned first in its
own scratch folder, then each step through the real tools (each call's input and output checked by the
verifier, as the host does), then the verdict on what the submit step hands in.

A case is JSON: {"today", "request", "world"?, "steps": [...], "expect": {...}}. "today" is the booking
date the clock reads; "world", when given, replaces the simulated offers with hand-built ones, in the tools
and the verifier alike: {"route": [origin, destination], "offers": {date: [offers]}}. A step is one of
  {"tool": name, "arguments": {...} or "$request", "save_as": name}  - "$ref:<save_as>.<key>..." strings resolve
  {"tamper": {"file": "<run file>", "set": {...}}}                    - edits a receipt behind the tools' back
  {"pin_answer_key": true}                                            - pins the answer key here instead of first
  {"submit": {...}}                                                   - the agent's submission
"""

from __future__ import annotations

import itertools
import json
import tempfile
from contextlib import ExitStack, contextmanager
from pathlib import Path

from helpers import hand_built
from slimconfig import build_output, plain_output

import verifier
from contract import TASKS, TOOLS, Task, Tool
from plugin import booking_requirements, get_trip, receipts, search_flights, solve_booking

IMPLEMENTATIONS = {
    Tool.BOOKING_REQUIREMENTS: booking_requirements,
    Tool.GET_TRIP: get_trip,
    Tool.SEARCH_FLIGHTS: search_flights,
    Tool.SOLVE_BOOKING: solve_booking,
}
TASK = Task.BOOK_FLIGHT


def resolve(value, saved, request):
    if value == "$request":
        return request
    if isinstance(value, str) and value.startswith("$ref:"):
        node = saved
        for part in value[5:].split("."):
            node = node[int(part)] if isinstance(node, list) else node[part]
        return node
    if isinstance(value, list):
        return [resolve(item, saved, request) for item in value]
    if isinstance(value, dict):
        return {key: resolve(item, saved, request) for key, item in value.items()}
    return value


@contextmanager
def frozen_clock(today: str):
    """The clock reads ``today``, ticking one second per reading."""
    ticks = itertools.count()
    saved = receipts.CLOCK
    receipts.CLOCK = lambda: f"{today} 12:00:{next(ticks):02d}.000000"
    try:
        yield
    finally:
        receipts.CLOCK = saved


def call(tool: Tool, arguments: dict, workspace: Path) -> dict:
    """One tool call as the host makes it; raises with the verifier's message when a check refuses it."""
    given, made = TOOLS[tool]
    value = build_output(arguments, given)
    check = verifier.verify_input(tool.value, value)
    if not check["valid"]:
        raise ValueError(f"{tool.value} input refused: {check['message']}")
    output = IMPLEMENTATIONS[tool](value, workspace)
    check = verifier.verify_output(tool.value, build_output(arguments, given), build_output(plain_output(output), made),
                                   str(workspace))
    if not check["valid"]:
        raise ValueError(f"{tool.value} output refused: {check['message']}")
    return plain_output(output)


def replay(case: dict) -> dict:
    """The case's verdict, or {"error": message} when a tool call is refused."""
    with ExitStack() as stack:
        stack.enter_context(frozen_clock(case["today"]))
        if "world" in case:
            stack.enter_context(hand_built(case["world"]["offers"], *case["world"]["route"]))
        root = Path(stack.enter_context(tempfile.TemporaryDirectory()))
        return run_steps(case, root)


def run_steps(case: dict, root: Path) -> dict:
    workspace, scratch = root / "workspace", root / "scratch"
    workspace.mkdir()
    scratch.mkdir()
    request = case["request"]
    steps = case["steps"]
    key = None
    try:
        if not any("pin_answer_key" in step for step in steps):
            key = call(Tool.SOLVE_BOOKING, request, scratch)
        saved: dict = {}
        submission = None
        for step in steps:
            if "pin_answer_key" in step:
                key = call(Tool.SOLVE_BOOKING, request, scratch)
            elif "tool" in step:
                output = call(Tool(step["tool"]), resolve(step["arguments"], saved, request), workspace)
                if "save_as" in step:
                    saved[step["save_as"]] = output
            elif "tamper" in step:
                run_id = saved["trip"]["run_id"]
                path = workspace / "runs" / run_id / step["tamper"]["file"]
                value = json.loads(path.read_text())
                value.update(step["tamper"]["set"])
                path.write_text(json.dumps(value))
            elif "submit" in step:
                submission = resolve(step["submit"], saved, request)
    except ValueError as error:
        return {"error": str(error)}
    if submission is None:
        return {"error": "no submission: the task fails without submit"}
    given, made = TASKS[TASK]
    return verifier.verify_task(TASK.value, build_output(request, given), build_output(submission, made),
                                build_output(key, TOOLS[Tool.SOLVE_BOOKING][1]), str(workspace))


def matches(verdict: dict, expect: dict) -> list[str]:
    """How a verdict differs from what a case expects."""
    if "error_contains" in expect:
        if expect["error_contains"] not in verdict.get("error", ""):
            return [f"expected an error with {expect['error_contains']!r}, got {verdict}"]
        return []
    if "error" in verdict:
        return [f"unexpected error {verdict['error']}"]
    problems = []
    if verdict["valid"] is not expect["valid"]:
        problems.append(f"valid {verdict['valid']} != {expect['valid']}: {verdict['message']}")
    if abs(verdict["score"] - expect["score"]) > 1e-9:
        problems.append(f"score {verdict['score']} != {expect['score']}")
    failed = [entry["id"] for entry in verdict["details"]["checks"] if entry["ok"] is False]
    if failed != expect["failed"]:
        problems.append(f"failed checks {failed} != {expect['failed']}")
    return problems
