"""Rules M2-M5 on hand-built trips and offers, every boundary included."""

from __future__ import annotations

import pytest
from helpers import request

from contract import Airport, Cabin, Offer, Refusal, Segment, Trip
from plugin import world
from plugin.rules import (
    booking_date_problem,
    clock_minutes,
    date_of,
    day_number,
    local_text,
    minute_number,
    request_problem,
    search_days,
    solve,
    time_text,
    trip_matches_request,
    window,
)

BOSTON = Airport("BOS", "Boston Logan", "Boston", "US", -300)
CHICAGO = Airport("ORD", "O'Hare", "Chicago", "US", -360)
LONDON = Airport("LHR", "Heathrow", "London", "GB", 0)


def trip(*, booking="2027-03-01", arrival="2027-03-20", start="13:00", end="17:00", approval=False,
         destination=BOSTON) -> Trip:
    earliest, latest = window(arrival, start, end, destination.utc_offset_minutes)
    days = search_days(earliest, latest, CHICAGO.utc_offset_minutes, world.journey_minutes("ORD", destination.code),
                       booking)
    return Trip("Test Traveller", CHICAGO, destination, booking, arrival, day_number(arrival) - day_number(booking),
                start, end, time_text(earliest), time_text(latest), *days, approval)


def offer(offer_id, fare, arrive, *, cabin=Cabin.ECONOMY, refundable=False, change_fee=0, depart=None) -> Offer:
    """A nonstop Chicago-Boston offer landing at ``arrive`` (UTC), by default leaving 125 minutes earlier."""
    depart = depart or time_text(minute_number(arrive) - 125)
    segment = Segment("ORD", "BOS", "TA 1", depart, arrive, 125)
    return Offer(offer_id, "Test Air", cabin, fare, refundable, change_fee, 125,
                 local_text(minute_number(depart), -360), local_text(minute_number(arrive), -300), [segment])


def test_dates_and_times_round_trip_and_reject_impossible_values() -> None:
    for text in ("1970-01-01", "2000-02-29", "2027-12-31", "2028-02-29", "2100-03-01"):
        assert date_of(day_number(text)) == text
    for bad in ("2027-02-29", "2027-13-01", "2027-1-01", "tomorrow"):
        with pytest.raises(ValueError):
            day_number(bad)
    assert time_text(minute_number("2027-01-01 23:59")) == "2027-01-01 23:59"
    assert clock_minutes("00:00") == 0 and clock_minutes("23:59") == 1439
    for bad in ("24:00", "7:30", "12:60", "noon"):
        with pytest.raises(ValueError):
            clock_minutes(bad)


def test_the_window_is_local_time_widened_by_90_minutes_in_utc() -> None:
    t = trip()  # Boston is UTC-5: 13:00-17:00 local is 18:00-22:00 UTC
    assert (t.window_earliest, t.window_latest) == ("2027-03-20 16:30", "2027-03-20 23:30")
    london = trip(destination=LONDON, start="00:30", end="23:00")
    assert (london.window_earliest, london.window_latest) == ("2027-03-19 23:00", "2027-03-21 00:30")


@pytest.mark.parametrize(("arrive", "inside"), [
    ("2027-03-20 16:29", False), ("2027-03-20 16:30", True), ("2027-03-20 23:30", True), ("2027-03-20 23:31", False),
])
def test_landing_exactly_90_minutes_outside_the_window_counts_and_91_does_not(arrive, inside) -> None:
    answer = solve(trip(), [offer("A", 10_000, arrive), offer("B", 90_000, "2027-03-20 20:00")])
    assert ("A" in answer.correct) is inside
    assert answer.correct == (["A"] if inside else ["B"])


def test_the_cheapest_overall_outside_the_window_is_not_booked() -> None:
    offers = [offer("CHEAP", 5_000, "2027-03-21 02:00"), offer("IN", 30_000, "2027-03-20 20:00")]
    assert solve(trip(), offers).correct == ["IN"]


def test_a_flight_leaving_the_previous_local_day_that_lands_in_the_window_is_a_candidate() -> None:
    """To London (UTC+0) landing 07:00-10:00: an overnight flight leaving Chicago at 18:00 local the day before
    lands in the window and is a candidate. No flight leaving on the arrival date can land that early, so the
    trip's departure days are the day before only."""
    t = trip(destination=LONDON, start="07:00", end="10:00")
    assert (t.search_from, t.search_to) == ("2027-03-19", "2027-03-19")
    overnight = offer("EVE", 50_000, "2027-03-20 08:30", depart="2027-03-20 00:00")
    assert overnight.depart_local == "2027-03-19 18:00"
    answer = solve(t, [overnight, offer("DEAR", 90_000, "2027-03-20 09:00", depart="2027-03-20 01:00")])
    assert answer.in_window == ["EVE", "DEAR"] and answer.correct == ["EVE"]


def test_a_flight_leaving_outside_the_departure_days_does_not_count() -> None:
    t = trip()
    assert (t.search_from, t.search_to) == ("2027-03-20", "2027-03-20")
    early = offer("EARLY", 5_000, "2027-03-20 17:00", depart="2027-03-19 05:00")  # 2027-03-18 23:00 local
    assert solve(t, [early, offer("IN", 30_000, "2027-03-20 20:00")]).correct == ["IN"]


@pytest.mark.parametrize(("booking", "first"), [("2027-03-01", "2027-03-19"), ("2027-03-20", "2027-03-20")])
def test_departure_days_never_start_before_today(booking, first) -> None:
    assert trip(booking=booking, destination=LONDON, start="07:00", end="10:00").search_from == first


def test_the_lowest_fare_wins_whatever_its_cabin_and_restrictions() -> None:
    offers = [offer("FLEX", 40_000, "2027-03-20 19:00", refundable=True),
              offer("SAVER", 25_000, "2027-03-20 20:00", change_fee=20_000),
              offer("BIZ", 24_999, "2027-03-20 21:00", cabin=Cabin.BUSINESS)]
    answer = solve(trip(), offers)
    assert answer.correct == ["BIZ"] and answer.lowest_fare_cents == 24_999
    assert answer.in_window == ["FLEX", "SAVER", "BIZ"]


def test_tied_lowest_fares_are_all_correct() -> None:
    offers = [offer("A", 25_000, "2027-03-20 19:00"), offer("B", 25_000, "2027-03-20 21:00"),
              offer("C", 25_001, "2027-03-20 20:00")]
    assert solve(trip(), offers).correct == ["A", "B"]


@pytest.mark.parametrize(("booking", "required"), [("2027-03-13", False), ("2027-03-14", True), ("2027-03-20", True),
                                                   ("2027-02-01", False)])
def test_approval_is_required_under_7_days_and_exactly_7_is_not(booking, required) -> None:
    t = trip(booking=booking)
    answer = solve(t, [offer("A", 25_000, "2027-03-20 20:00")])
    assert answer.approval_required is required
    assert answer.refusal is (Refusal.NO_SVP_APPROVAL if required else Refusal.NONE)


def test_approval_held_lets_a_short_notice_ticket_be_booked() -> None:
    answer = solve(trip(booking="2027-03-18", approval=True), [offer("A", 25_000, "2027-03-20 20:00")])
    assert answer.refusal is Refusal.NONE and answer.approval_required is True and answer.correct == ["A"]


def test_approval_is_checked_before_the_window() -> None:
    answer = solve(trip(booking="2027-03-18"), [])
    assert answer.refusal is Refusal.NO_SVP_APPROVAL


def test_nothing_in_the_window_is_refused() -> None:
    answer = solve(trip(), [offer("LATE", 5_000, "2027-03-21 02:00")])
    assert answer.refusal is Refusal.NO_FLIGHT_IN_WINDOW and answer.correct == []
    assert solve(trip(), []).refusal is Refusal.NO_FLIGHT_IN_WINDOW


def test_a_request_is_checked_without_a_clock() -> None:
    assert request_problem(request()) is None
    assert request_problem(request(arrive_from="15:00", arrive_to="15:00")) is None
    for changes, words in (
        ({"traveller_name": "  "}, "blank"),
        ({"traveller_name": "x" * 81}, "longer"),
        ({"destination": "ORD"}, "both ORD"),
        ({"arrival_date": "2026-02-30"}, "not a real"),
        ({"arrive_from": "9:00"}, "HH:MM"),
        ({"arrive_to": "24:00"}, "HH:MM"),
        ({"arrive_from": "17:00", "arrive_to": "13:00"}, "before arrive_from"),
    ):
        assert words in request_problem(request(**changes)), changes


@pytest.mark.parametrize(("date", "ok"), [("2026-11-05", True), ("2026-11-04", False), ("2027-10-01", True),
                                          ("2027-10-02", False)])
def test_arrivals_run_from_today_to_330_days_ahead(date, ok) -> None:
    assert (booking_date_problem(date, "2026-11-05") is None) is ok


def test_a_trip_matches_its_request_only_with_its_window_and_days_ahead() -> None:
    value = request(arrival_date="2027-03-20", traveller_name="Test Traveller")
    moved = trip(booking="2027-03-01")
    moved.window_latest = "2027-03-20 23:31"
    assert not trip_matches_request(moved, value, world.journey_minutes("ORD", "BOS"))
    journey = world.journey_minutes("ORD", "BOS")
    good = trip(booking="2027-03-01")
    assert trip_matches_request(good, value, journey)
    for name, wrong in (("days_ahead", 18), ("search_from", "2027-03-19"), ("search_to", "2027-03-21")):
        bad = trip(booking="2027-03-01")
        setattr(bad, name, wrong)
        assert not trip_matches_request(bad, value, journey), name
