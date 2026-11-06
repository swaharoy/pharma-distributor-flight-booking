"""The verifier on correct, wrong, missing, malformed, tampered and boundary results, built the way the
sandbox builds them (build_output of plain JSON). Real simulated offers where they show the case, and
hand-built offers (in the tools and the verifier alike) for exact boundaries."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest
from helpers import Run, booking, failed, hand_built, judge, offer, request, requests, tool_input
from slimconfig import build_output, plain_output

import verifier
from contract import (
    AirportCode,
    RequirementsInput,
    RequirementsOutput,
    SearchInput,
    SearchOutput,
    SolveOutput,
    Topic,
    TripOutput,
)
from plugin import booking_requirements, get_trip, search_flights, solve_booking
from plugin.rules import in_window


def valid(verdict: dict) -> bool:
    return verdict["valid"] is True and verdict["score"] == 1.0


def refused(verdict: dict, *check_ids: str) -> bool:
    return verdict["valid"] is False and verdict["score"] == 0.0 and failed(verdict) == list(check_ids)


def first_request(test, salt: str):
    """The first varied request whose answer key passes ``test(key)``."""
    with tempfile.TemporaryDirectory() as folder:
        for value in requests(3000, salt):
            if test(solve_booking(value, Path(folder))):
                return value
    raise LookupError(salt)


def bookable(key) -> bool:
    return key.refusal.value == "NONE"


# Correct --------------------------------------------------------------------------------------------


def test_the_gold_booking_is_valid_for_varied_requests(tmp_path: Path) -> None:
    refusals = set()
    for index, value in enumerate(requests(80, "gold")):
        run = Run(value, tmp_path / str(index))
        verdict = run.judge(run.gold())
        assert valid(verdict), (plain_output(value), verdict["message"])
        assert all(entry["ok"] is True for entry in verdict["details"]["checks"])
        refusals.add(run.key.refusal.value)
    assert refusals == {"NONE", "NO_SVP_APPROVAL", "NO_FLIGHT_IN_WINDOW"}


def test_exactly_the_correct_offers_pass(tmp_path: Path) -> None:
    """Every offer the agent could book from its search is judged: valid if and only if the answer key lists it
    as correct (ties included)."""
    judged = 0
    for index, value in enumerate(requests(120, "every-offer")):
        run = Run(value, tmp_path / str(index))
        if not bookable(run.key):
            continue
        for found in run.offers:
            verdict = run.judge(run.book(found.offer_id))
            assert verdict["valid"] is (found.offer_id in run.key.correct_offer_ids), (index, found.offer_id)
            judged += 1
    assert judged > 300


def test_a_short_notice_trip_without_approval_is_refused_without_searching(tmp_path: Path) -> None:
    run = Run(request(arrival_date="2026-11-08"), tmp_path, search=False)
    assert run.key.refusal.value == "NO_SVP_APPROVAL" and run.key.svp_approval_required is True
    assert valid(run.judge(booking(run.run_id, booked=False, refusal="NO_SVP_APPROVAL", required=True)))


def test_a_short_notice_trip_with_approval_is_booked_and_flags_the_approval(tmp_path: Path) -> None:
    value = first_request(lambda k: bookable(k) and k.svp_approval_required, "approved")
    run = Run(value, tmp_path)
    assert valid(run.judge(run.gold()))
    assert refused(run.judge(run.gold() | {"svp_approval_required": False}), "approval")


# Wrong, on real simulated offers -----------------------------------------------------------------------


def test_a_refundable_fare_instead_of_a_cheaper_restricted_one_is_refused(tmp_path: Path) -> None:
    value = first_request(lambda k: bookable(k) and any(
        o.refundable and o.offer_id in k.window_offer_ids and o.fare_cents > k.lowest_fare_cents for o in k.offers)
        and not any(o.refundable for o in k.offers if o.offer_id in k.correct_offer_ids), "refundable")
    run = Run(value, tmp_path)
    chosen = next(o for o in run.offers if o.refundable and o.offer_id in run.key.window_offer_ids)
    verdict = run.judge(run.book(chosen.offer_id))
    assert refused(verdict, "fare") and "refundability" in verdict["message"]


def test_the_cheapest_flight_landing_outside_the_window_is_refused(tmp_path: Path) -> None:
    value = first_request(lambda k: bookable(k) and min(o.fare_cents for o in k.offers) < k.lowest_fare_cents, "cheap")
    run = Run(value, tmp_path)
    cheapest = min(run.offers, key=lambda o: o.fare_cents)
    assert not in_window(run.trip, cheapest)
    verdict = run.judge(run.book(cheapest.offer_id))
    assert refused(verdict, "window") and ("early" in verdict["message"] or "late" in verdict["message"])


def test_a_dearer_fare_in_the_window_is_refused(tmp_path: Path) -> None:
    value = first_request(lambda k: bookable(k) and len({o.fare_cents for o in k.offers
                                                         if o.offer_id in k.window_offer_ids}) > 1, "dearer")
    run = Run(value, tmp_path)
    dearer = next(o for o in run.offers if o.offer_id in run.key.window_offer_ids
                  and o.fare_cents > run.key.lowest_fare_cents)
    assert refused(run.judge(run.book(dearer.offer_id)), "fare")


def test_booking_without_required_approval_is_refused(tmp_path: Path) -> None:
    run = Run(request(arrival_date="2026-11-08"), tmp_path)
    verdict = run.judge(booking(run.run_id, run.offers[0].offer_id, required=True))
    assert refused(verdict, "refusal") and "Senior VP" in verdict["message"]


@pytest.mark.parametrize("required", [True, False])
def test_a_wrong_approval_flag_is_refused(tmp_path: Path, required: bool) -> None:
    arrival = "2026-11-08" if not required else "2026-12-03"  # 3 days ahead needs approval; 28 days does not
    run = Run(request(arrival_date=arrival, svp_approval=True), tmp_path)
    assert refused(run.judge(run.gold() | {"svp_approval_required": required}), "approval")


@pytest.mark.parametrize("refusal", ["NO_FLIGHT_IN_WINDOW", "NO_SVP_APPROVAL"])
def test_refusing_a_bookable_trip_is_refused(tmp_path: Path, refusal: str) -> None:
    run = Run(request(), tmp_path)
    assert bookable(run.key)
    assert refused(run.judge(booking(run.run_id, booked=False, refusal=refusal)), "refusal")


def test_booking_when_nothing_lands_in_the_window_is_refused(tmp_path: Path) -> None:
    value = first_request(lambda k: k.refusal.value == "NO_FLIGHT_IN_WINDOW" and k.offers, "empty")
    run = Run(value, tmp_path)
    verdict = run.judge(run.book(run.offers[0].offer_id))
    assert refused(verdict, "refusal") and "no flight" in verdict["message"]


@pytest.mark.parametrize(
    "changes",
    [
        {"booked": True, "refusal": "NO_FLIGHT_IN_WINDOW"},
        {"booked": False, "refusal": "NONE"},
        {"booked": False, "refusal": "NO_FLIGHT_IN_WINDOW", "offer_id": "20261203-01"},
    ],
)
def test_an_inconsistent_booking_or_refusal_is_refused(tmp_path: Path, changes: dict) -> None:
    run = Run(request(), tmp_path)
    verdict = run.judge(run.gold() | changes)
    assert verdict["valid"] is False and failed(verdict)[0] == "refusal"


def test_an_offer_leaving_another_day_is_refused(tmp_path: Path) -> None:
    run = Run(request(), tmp_path)
    earlier = run.search("2026-12-02", "2026-12-02").offers[0]
    verdict = run.judge(run.book(earlier.offer_id))
    assert refused(verdict, "window") and "outside the trip's departure days" in verdict["message"]


def test_a_flight_leaving_the_previous_local_day_is_judged_like_any_other(tmp_path: Path) -> None:
    """Newark to London landing 07:00-10:00: the overnight flight leaving 2026-12-02 is a candidate; booking the
    lowest of them passes, and searching only the arrival date misses them."""
    run = Run(request(origin="EWR", destination="LHR", arrive_from="07:00", arrive_to="10:00"), tmp_path)
    assert run.trip.search_from == "2026-12-02"
    previous = [o for o in run.offers if o.offer_id in run.key.window_offer_ids and o.depart_local[:10] == "2026-12-02"]
    assert previous
    assert valid(run.judge(run.gold()))
    for found in previous:
        verdict = run.judge(run.book(found.offer_id))
        assert verdict["valid"] is (found.offer_id in run.key.correct_offer_ids), found.offer_id


def test_an_offer_on_another_route_is_refused(tmp_path: Path) -> None:
    run = Run(request(), tmp_path)
    elsewhere = run.search(origin="JFK").offers[0]
    verdict = run.judge(run.book(elsewhere.offer_id))
    assert refused(verdict, "offer-seen") and "not the trip's route" in verdict["message"]


# Exact boundaries, on hand-built offers -----------------------------------------------------------------


def boundary(tmp_path: Path, offers: list[dict], value, output) -> tuple[dict, SolveOutput]:
    by_day: dict[str, list[dict]] = {}
    for one in offers:
        by_day.setdefault(one["depart_local"][:10], []).append(one)
    with hand_built(by_day, value.origin.value, value.destination.value):
        run = Run(value, tmp_path)
        out = output if isinstance(output, dict) else run.book(output)
        return run.judge(out | {"run_id": run.run_id}), run.key


# The default request: arrive in Boston 13:00-17:00 local (UTC-5) on 2026-12-03, so the widened window is
# 2026-12-03 16:30 to 23:30 UTC.
@pytest.mark.parametrize(("arrive", "inside"), [("2026-12-03 16:30", True), ("2026-12-03 16:29", False),
                                                ("2026-12-03 23:30", True), ("2026-12-03 23:31", False)])
def test_landing_exactly_90_minutes_outside_passes_and_91_fails(tmp_path: Path, arrive: str, inside: bool) -> None:
    offers = [offer("20261203-01", 20_000, arrive=arrive), offer("20261203-02", 40_000)]
    verdict, key = boundary(tmp_path, offers, request(), "20261203-01")
    assert (key.correct_offer_ids == ["20261203-01"]) is inside
    assert valid(verdict) if inside else refused(verdict, "window")


@pytest.mark.parametrize(("arrival", "required"), [("2026-11-12", False), ("2026-11-11", True)])
def test_exactly_7_days_ahead_needs_no_approval_and_6_does(tmp_path: Path, arrival: str, required: bool) -> None:
    offers = [offer(arrival.replace("-", "") + "-01", 20_000, arrive=f"{arrival} 20:00")]
    value = request(arrival_date=arrival)
    verdict, key = boundary(tmp_path / "a", offers, value, offers[0]["offer_id"])
    assert key.svp_approval_required is required
    assert valid(verdict) if not required else refused(verdict, "refusal")  # booked without approval
    refusal = booking("", booked=False, refusal="NO_SVP_APPROVAL", required=True)
    verdict, _ = boundary(tmp_path / "b", offers, value, refusal)
    assert valid(verdict) if required else refused(verdict, "approval")


def test_six_days_ahead_with_approval_is_booked(tmp_path: Path) -> None:
    offers = [offer("20261111-01", 20_000, arrive="2026-11-11 20:00")]
    verdict, _ = boundary(tmp_path, offers, request(arrival_date="2026-11-11", svp_approval=True),
                          booking("", "20261111-01", required=True))
    assert valid(verdict)


def test_the_most_restricted_fare_is_right_when_it_is_the_lowest(tmp_path: Path) -> None:
    offers = [offer("20261203-01", 30_000, refundable=True), offer("20261203-02", 29_999, change_fee=20_000)]
    assert valid(boundary(tmp_path / "a", offers, request(), "20261203-02")[0])
    assert refused(boundary(tmp_path / "b", offers, request(), "20261203-01")[0], "fare")


def test_a_business_fare_below_economy_is_right(tmp_path: Path) -> None:
    offers = [offer("20261203-01", 30_000), offer("20261203-02", 29_000, cabin="BUSINESS")]
    assert valid(boundary(tmp_path, offers, request(), "20261203-02")[0])


def test_tied_lowest_fares_both_pass(tmp_path: Path) -> None:
    offers = [offer("20261203-01", 30_000, arrive="2026-12-03 18:00"), offer("20261203-02", 30_000),
              offer("20261203-03", 30_001)]
    assert valid(boundary(tmp_path / "a", offers, request(), "20261203-01")[0])
    assert valid(boundary(tmp_path / "b", offers, request(), "20261203-02")[0])
    assert refused(boundary(tmp_path / "c", offers, request(), "20261203-03")[0], "fare")


def test_an_empty_window_means_no_flight_in_window(tmp_path: Path) -> None:
    offers = [offer("20261203-01", 10_000, arrive="2026-12-03 15:00"), offer("20261203-02", 10_000,
                                                                             arrive="2026-12-04 01:00")]
    verdict, key = boundary(tmp_path / "a", offers, request(),
                            booking("", booked=False, refusal="NO_FLIGHT_IN_WINDOW"))
    assert key.refusal.value == "NO_FLIGHT_IN_WINDOW" and valid(verdict)
    assert refused(boundary(tmp_path / "b", offers, request(), "20261203-01")[0], "refusal")


# Missing --------------------------------------------------------------------------------------------


def test_booking_without_a_search_is_refused(tmp_path: Path) -> None:
    run = Run(request(), tmp_path, search=False)
    assert refused(run.judge(run.book(run.key.correct_offer_ids[0])), "searched")


def test_refusing_for_no_flight_without_a_search_is_refused(tmp_path: Path) -> None:
    run = Run(request(), tmp_path, search=False)
    assert refused(run.judge(booking(run.run_id, booked=False, refusal="NO_FLIGHT_IN_WINDOW")), "searched")


@pytest.mark.parametrize("offer_id", ["20261203-99", "", "F01"])
def test_an_offer_never_returned_is_refused(tmp_path: Path, offer_id: str) -> None:
    run = Run(request(), tmp_path)
    assert refused(run.judge(run.book(offer_id)), "offer-seen")


@pytest.mark.parametrize("run_id", ["0123456789ab", "not-a-run", ""])
def test_a_run_that_does_not_exist_is_refused(tmp_path: Path, run_id: str) -> None:
    run = Run(request(), tmp_path)
    assert refused(run.judge(run.gold() | {"run_id": run_id}), "this-run")


def test_no_answer_key_is_refused(tmp_path: Path) -> None:
    run = Run(request(), tmp_path)
    assert refused(judge(run.request, run.gold(), None, run.workspace), "answer-key")


def test_an_answer_key_for_another_request_is_refused(tmp_path: Path) -> None:
    run = Run(request(), tmp_path)
    assert refused(judge(request(arrive_to="18:00"), run.gold(), run.key, run.workspace), "answer-key")


# Tampering ------------------------------------------------------------------------------------------


def edit(path: Path, **changes) -> None:
    value = json.loads(path.read_text())
    value.update(changes)
    path.write_text(json.dumps(value))


@pytest.mark.parametrize("changes", [{"digest": "0" * 64}, {"offer_ids": []}, {"origin": "XXX"}, {"date_to": "x"},
                                     {"date_from": "2026-12-04"}])
def test_a_tampered_search_receipt_is_refused(tmp_path: Path, changes: dict) -> None:
    run = Run(request(), tmp_path)
    edit(run.workspace / "runs" / run.run_id / "search-1.json", **changes)
    assert refused(run.judge(run.gold()), "receipts-match")


def test_a_run_begun_before_the_answer_key_is_refused(tmp_path: Path) -> None:
    run = Run(request(), tmp_path)
    edit(run.workspace / "runs" / run.run_id / "trip.json", started_at="2026-11-05 00:00:00.000000")
    verdict = run.judge(run.gold())
    assert refused(verdict, "this-run") and "earlier run" in verdict["message"]


def test_a_run_booked_on_another_day_is_refused(tmp_path: Path) -> None:
    run = Run(request(), tmp_path)
    edit(run.workspace / "runs" / run.run_id / "trip.json", booking_date="2026-11-04")
    assert refused(run.judge(run.gold()), "this-run")


def test_a_run_of_another_request_is_refused(tmp_path: Path) -> None:
    other = Run(request(svp_approval=True), tmp_path / "other")
    run = Run(request(), tmp_path)
    verdict = judge(run.request, run.gold() | {"run_id": other.run_id}, run.key, other.workspace)
    assert refused(verdict, "this-run")


def test_a_tampered_answer_key_is_refused(tmp_path: Path) -> None:
    run = Run(request(), tmp_path)
    run.key.correct_offer_ids = [o.offer_id for o in run.key.offers]
    assert refused(run.judge(run.gold()), "answer-key")


def test_an_answer_key_with_a_moved_window_is_refused(tmp_path: Path) -> None:
    run = Run(request(), tmp_path)
    run.key.trip.window_latest = "2026-12-04 05:00"
    assert refused(run.judge(run.gold()), "answer-key")


def test_an_answer_key_with_edited_offers_is_refused(tmp_path: Path) -> None:
    run = Run(request(), tmp_path)
    run.key.offers[0].fare_cents += 1
    assert refused(run.judge(run.gold()), "answer-key")


# Determinism and the tools' own checks -----------------------------------------------------------------


def test_the_verdict_is_the_same_twice(tmp_path: Path) -> None:
    run = Run(request(), tmp_path)
    for output in (run.gold(), run.book(run.offers[0].offer_id)):
        assert json.dumps(run.judge(output), sort_keys=True) == json.dumps(run.judge(output), sort_keys=True)


def test_tool_inputs_are_checked() -> None:
    good = plain_output(request())
    assert tool_input("get_trip", good)["valid"] is True
    for bad in ({"destination": "ORD"}, {"arrival_date": "2026-02-30"}, {"arrive_from": "1:00"},
                {"arrive_from": "18:00"}, {"arrive_to": "25:00"}, {"traveller_name": " "}):
        assert tool_input("get_trip", good | bad)["valid"] is False, bad
        assert tool_input("solve_booking", good | bad)["valid"] is False, bad
    query = {"run_id": "", "origin": "JFK", "destination": "LAX", "date_from": "2027-03-01", "date_to": "2027-03-08"}
    assert tool_input("search_flights", query)["valid"] is True
    assert tool_input("search_flights", query | {"run_id": "0123456789ab"})["valid"] is True
    for bad in ({"date_to": "2027-03-09"}, {"date_to": "2027-02-28"}, {"date_from": "2027-02-30"},
                {"run_id": "nope"}, {"destination": "JFK"}):
        assert tool_input("search_flights", query | bad)["valid"] is False, bad
    for topic in Topic:
        assert tool_input("booking_requirements", {"topic": topic.value})["valid"] is True


def test_tool_outputs_are_checked(tmp_path: Path) -> None:
    run = Run(request(), tmp_path)
    trip_out = build_output(plain_output(TripOutput(run.run_id, run.trip)), TripOutput)
    assert verifier.verify_output("get_trip", run.request, trip_out, str(run.workspace))["valid"] is True
    assert verifier.verify_output("get_trip", request(svp_approval=True), trip_out,
                                  str(run.workspace))["valid"] is False
    for change in ({"booking_date": "2026-12-04"}, {"days_ahead": 27}, {"window_earliest": "2026-12-03 16:31"},
                   {"search_from": "2026-12-02"}, {"search_to": "2026-12-04"}):
        moved = build_output(plain_output(trip_out) | {"trip": plain_output(run.trip) | change}, TripOutput)
        assert verifier.verify_output("get_trip", run.request, moved, str(run.workspace))["valid"] is False, change
    query = SearchInput(run.run_id, AirportCode.ORD, AirportCode.BOS, run.trip.search_from, run.trip.search_to)
    found = build_output(plain_output(SearchOutput(run.run_id, "Simulated fares and schedules; airline names are "
                                                   "used for realism only.", run.offers)), SearchOutput)
    assert verifier.verify_output("search_flights", query, found, str(run.workspace))["valid"] is True
    shifted = SearchInput(run.run_id, AirportCode.ORD, AirportCode.BOS, run.trip.arrival_date, "2026-12-04")
    assert verifier.verify_output("search_flights", shifted, found, str(run.workspace))["valid"] is False
    found.offers[0].refundable = not found.offers[0].refundable
    assert verifier.verify_output("search_flights", query, found, str(run.workspace))["valid"] is False
    found.offers[0].refundable = not found.offers[0].refundable
    found.note = "Real fares."
    assert verifier.verify_output("search_flights", query, found, str(run.workspace))["valid"] is False
    key = build_output(plain_output(run.key), SolveOutput)
    assert verifier.verify_output("solve_booking", run.request, key, str(tmp_path))["valid"] is True
    key.svp_approval_required = not key.svp_approval_required
    assert verifier.verify_output("solve_booking", run.request, key, str(tmp_path))["valid"] is False


@pytest.mark.parametrize("topic", list(Topic))
def test_the_requirements_are_checked(tmp_path: Path, topic: Topic) -> None:
    given = RequirementsInput(topic)
    made = build_output(plain_output(booking_requirements(given, tmp_path)), RequirementsOutput)
    assert verifier.verify_output("booking_requirements", given, made, str(tmp_path))["valid"] is True
    assert verifier.verify_task("booking-requirements", given, made, None, str(tmp_path))["valid"] is True
    for change in ({"today": "2026-13-01"}, {"example_request": "Book anything."},
                   {"airports": [] if topic is not Topic.FIELDS else [{"code": "BOS", "name": "x", "city": "y",
                                                                         "country": "US"}]}):
        altered = build_output(plain_output(made) | change, RequirementsOutput)
        assert verifier.verify_output("booking_requirements", given, altered, str(tmp_path))["valid"] is False, change


def test_tool_tasks_are_judged_as_their_tools(tmp_path: Path) -> None:
    query = SearchInput("", AirportCode.JFK, AirportCode.LAX, "2026-12-01", "2026-12-02")
    found = build_output(plain_output(search_flights(query, tmp_path)), SearchOutput)
    assert verifier.verify_task("search-flights", query, found, None, str(tmp_path))["valid"] is True
    other = SearchInput("", AirportCode.JFK, AirportCode.SFO, "2026-12-01", "2026-12-02")
    assert verifier.verify_task("search-flights", other, found, None, str(tmp_path))["valid"] is False


def test_tools_refuse_past_and_far_dates(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="before today"):
        get_trip(request(arrival_date="2026-11-04"), tmp_path)
    with pytest.raises(ValueError, match="330 days"):
        get_trip(request(arrival_date="2027-10-02"), tmp_path)
    with pytest.raises(ValueError, match="before today"):
        search_flights(SearchInput("", AirportCode.JFK, AirportCode.LAX, "2026-11-01", "2026-11-02"), tmp_path)
    with pytest.raises(ValueError, match="get_trip first"):
        search_flights(SearchInput("0123456789ab", AirportCode.JFK, AirportCode.LAX, "2026-12-01", "2026-12-02"),
                       tmp_path)
