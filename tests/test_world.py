"""The simulated world: real airports and airlines on plausible routes, synthetic but realistic fares, fare
rules and schedules, the same on every machine, and an answer key that agrees with an independent reading of
the rules."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import pytest
from helpers import CODES, request, requests
from oracle import booking_answer
from slimconfig import plain_output

from contract import AirportCode, SearchInput
from plugin import receipts, search_flights, solve_booking, world
from plugin.rules import date_of, day_number, minute_number, search_days, window
from plugin.trip import make_trip

DAY = day_number("2026-12-03")
GOLDEN = {
    ("ORD", "BOS"): "0e202e24f52e3c80",
    ("JFK", "LAX"): "4f40de0078da84b7",
    ("ATL", "ORD"): "870648c4f45469cf",
    ("SFO", "NRT"): "2ff63f42d39105e6",
    ("LHR", "CDG"): "0888746e5cf00b59",
    ("SYD", "JNB"): "77894a551eceb176",
}
US_AIRLINES = {row[1] for row in world.AIRLINES if row[2] == "US"}
FLIGHT_NUMBER = re.compile(r"^[A-Z0-9]{2} [1-9]\d{0,3}$")
LARGEST_SEARCH_CHARS = 50_000  # a full 8-day search must stay well inside the hosted model's 65,536-token budget
LARGEST_DAY_CHARS = 6_000  # one departure day on a route
LARGEST_BOOKING_SEARCH_CHARS = 16_000  # the booking agent's search: every day that can reach a whole-day window
MOST_DEPARTURE_DAYS = 3  # search_from to search_to, at most
WEST_COAST = ("LAX", "SFO", "SEA", "SAN", "LAS", "YVR")
ASIA = ("NRT", "ICN", "SIN", "HKG", "DEL", "BOM", "DXB")


def routes(step: int = 5):
    """Every ``step``-th route of all 68 x 67."""
    pairs = [(a, b) for a in CODES for b in CODES if a != b]
    return pairs[::step]


def digest(offers) -> str:
    text = json.dumps([plain_output(offer) for offer in offers], sort_keys=True)
    return hashlib.sha256(text.encode()).hexdigest()[:16]


@pytest.mark.parametrize("route", sorted(GOLDEN))
def test_a_route_and_day_make_the_same_offers_everywhere(route) -> None:
    assert digest(world.day_offers(*route, DAY)) == GOLDEN[route]


def test_the_airports_are_the_contract_codes() -> None:
    assert [row[0] for row in world.AIRPORTS] == [member.value for member in AirportCode]
    assert len(world.AIRPORTS) == 68
    assert all(-720 <= row[7] <= 720 and row[7] % 30 == 0 for row in world.AIRPORTS)
    assert world.airport("BOS").utc_offset_minutes == -300 and world.airport("LHR").utc_offset_minutes == 0


def test_the_airlines_are_real_names_with_hubs_among_the_airports() -> None:
    assert "Delta Air Lines" in US_AIRLINES and "British Airways" in {row[1] for row in world.AIRLINES}
    for code, _name, _country, kind, reach, hubs, cabins in world.AIRLINES:
        assert re.fullmatch(r"[A-Z0-9]{2}", code) and kind in ("us", "low", "intl") and reach > 0
        assert hubs and all(world.is_airport(hub) for hub in hubs), code
        assert cabins in ("Y", "YJ", "YJF")


def local_minute(time: str, code: str) -> int:
    return (minute_number(time) + world.airport_table()[code][7]) % 1440


def test_offers_are_well_formed_and_plausible() -> None:
    airline_of = {row[1]: row for row in world.AIRLINES}
    for origin, destination in routes():
        domestic = world.country(origin) == world.country(destination) == "US"
        for day in (DAY, DAY + 40):
            offers = world.day_offers(origin, destination, day)
            ids = [offer.offer_id for offer in offers]
            assert ids == [f"{date_of(day).replace('-', '')}-{n:02d}" for n in range(1, len(ids) + 1)]
            assert [o.segments[0].depart for o in offers] == sorted(o.segments[0].depart for o in offers)
            for offer in offers:
                first, last = offer.segments[0], offer.segments[-1]
                assert first.origin == origin and last.destination == destination
                assert offer.depart_local[:10] == date_of(day), "leaves on its local day at the origin"
                assert offer.depart_local == world.local_text(minute_number(first.depart), world.utc_offset(origin))
                assert offer.arrive_local == world.local_text(minute_number(last.arrive),
                                                              world.utc_offset(destination))
                assert offer.total_air_minutes == sum(s.air_minutes for s in offer.segments)
                assert offer.fare_cents > 0 and offer.change_fee_cents in (0, 7_500, 10_000, 20_000)
                assert offer.refundable is False or offer.change_fee_cents == 0, "a refundable fare changes free"
                assert 6 * 60 <= local_minute(first.depart, origin) <= 21 * 60 + 55, "leaves 06:00-21:55 local"
                for one, two in zip(offer.segments, offer.segments[1:]):
                    assert one.destination == two.origin
                    assert 45 <= minute_number(two.depart) - minute_number(one.arrive) <= 240
                airline = airline_of[offer.carrier]
                if domestic:
                    assert offer.carrier in US_AIRLINES, (origin, destination, offer.carrier)
                for segment in offer.segments:
                    assert FLIGHT_NUMBER.fullmatch(segment.flight_number)
                    assert segment.flight_number.startswith(airline[0] + " ")
                    inside = world.country(segment.origin) == world.country(segment.destination)
                    assert not inside or world.country(segment.origin) == airline[2], "no cabotage"
                if len(offer.segments) == 2:
                    assert offer.segments[0].destination in airline[5], "connects at the airline's hub"
                else:
                    assert origin in airline[5] or destination in airline[5]
                if offer.cabin.value == "FIRST":
                    assert "F" in airline[6]


def test_live_searches_hold_the_realistic_traps() -> None:
    """Across routes, the traps the policy is about turn up without being planted."""
    seen = set()
    for origin, destination in routes(3):
        offers = world.day_offers(origin, destination, DAY)
        economy = sorted(o.fare_cents for o in offers if o.cabin.value == "ECONOMY")
        flights = {}
        for o in offers:
            flights.setdefault(o.segments[0].flight_number + o.segments[0].depart, []).append(o)
        for same in flights.values():
            if any(o.refundable for o in same) and any(not o.refundable for o in same):
                seen.add("a refundable and a cheaper non-refundable fare on one flight")
        if any(o.cabin.value == "BUSINESS" and economy and o.fare_cents < economy[-1] for o in offers):
            seen.add("business cheaper than some economy fare")
        if any(o.cabin.value == "BUSINESS" and economy and o.fare_cents < economy[0] for o in offers):
            seen.add("business cheaper than every economy fare")
        if any(o.cabin.value == "FIRST" for o in offers):
            seen.add("first class")
        if any(o.change_fee_cents == 20_000 for o in offers):
            seen.add("a $200 change fee")
        if len({len(o.segments) for o in offers}) == 2:
            seen.add("a nonstop and a connection")
    assert seen == {"a refundable and a cheaper non-refundable fare on one flight",
                    "business cheaper than some economy fare", "business cheaper than every economy fare",
                    "first class", "a $200 change fee", "a nonstop and a connection"}


def test_searches_fit_the_hosted_context() -> None:
    largest_day = largest = 0
    for origin, destination in routes(11):
        offers = world.offers_between(origin, destination, date_of(DAY), date_of(DAY + 7))
        largest = max(largest, len(json.dumps([plain_output(offer) for offer in offers])))
        day = world.day_offers(origin, destination, DAY)
        largest_day = max(largest_day, len(json.dumps([plain_output(offer) for offer in day])))
    assert largest <= LARGEST_SEARCH_CHARS, largest
    assert largest_day <= LARGEST_DAY_CHARS, largest_day


def test_offers_do_not_depend_on_the_booking_date(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    query = SearchInput("", AirportCode.JFK, AirportCode.LAX, "2026-12-20", "2026-12-22")
    early = search_flights(query, tmp_path)
    monkeypatch.setattr(receipts, "CLOCK", lambda: "2026-12-19 08:00:00.000000")
    assert plain_output(search_flights(query, tmp_path)) == plain_output(early)


def test_unknown_or_equal_airports_are_refused() -> None:
    with pytest.raises(ValueError):
        world.day_offers("XXX", "LHR", DAY)
    with pytest.raises(ValueError):
        world.day_offers("BOS", "BOS", DAY)
    with pytest.raises(ValueError):
        world.offers_between("BOS", "LHR", "2026-12-03", "2026-12-11")


def test_the_answer_key_agrees_with_an_independent_reading_for_400_requests(tmp_path: Path) -> None:
    """The oracle reads every offer sold around the arrival date, not the trip's departure days, so the key's
    candidates must be complete: every flight landing in the window, whatever day it leaves."""
    outcomes = set()
    for value in requests(400, "oracle"):
        key = solve_booking(value, tmp_path)
        refusal, required, correct = booking_answer(key.trip)
        assert key.refusal.value == refusal, plain_output(value)
        assert key.svp_approval_required is required, plain_output(value)
        assert set(key.correct_offer_ids) == correct, plain_output(value)
        outcomes.add((key.refusal.value, key.svp_approval_required))
    assert {("NONE", False), ("NONE", True), ("NO_SVP_APPROVAL", True), ("NO_FLIGHT_IN_WINDOW", False)} <= outcomes


def local_departures(codes, destinations=None):
    """Local departure minutes of every offer from ``codes`` on two days, to a spread of destinations."""
    found = []
    for origin in codes:
        for destination in destinations or CODES[::4]:
            if destination == origin:
                continue
            for day in (DAY, DAY + 40):
                found.extend(local_minute(o.segments[0].depart, origin)
                             for o in world.day_offers(origin, destination, day))
    return found


def test_every_departure_leaves_06_00_to_21_55_local_time() -> None:
    minutes = local_departures(CODES)
    assert minutes and min(minutes) >= 6 * 60 and max(minutes) <= 21 * 60 + 55
    assert min(minutes) < 7 * 60 and max(minutes) > 21 * 60, "the whole day is used"


def test_west_coast_origins_have_departures_after_16_00_local() -> None:
    for origin in WEST_COAST:
        assert any(minute > 16 * 60 for minute in local_departures([origin])), origin
    assert any(minute >= 20 * 60 for minute in local_departures(WEST_COAST))


def test_asian_origins_have_departures_before_09_00_local() -> None:
    for origin in ASIA:
        assert any(minute < 9 * 60 for minute in local_departures([origin])), origin


def test_departure_days_cover_every_flight_that_can_land_in_the_window() -> None:
    """For every route and a whole-day window, every offer sold from 3 days before to 3 days after the arrival
    date that lands in the window leaves on a day from search_from to search_to, and those days are few."""
    today, arrival = "2026-11-05", "2026-12-03"
    for origin, destination in routes(7):
        earliest, latest = window(arrival, "00:00", "23:59", world.utc_offset(destination))
        first, last = search_days(earliest, latest, world.utc_offset(origin),
                                  world.journey_minutes(origin, destination), today)
        assert 1 <= day_number(last) - day_number(first) + 1 <= MOST_DEPARTURE_DAYS
        for day in range(day_number(arrival) - 3, day_number(arrival) + 4):
            for o in world.day_offers(origin, destination, day):
                if earliest <= minute_number(o.segments[-1].arrive) <= latest:
                    assert day_number(first) <= day <= day_number(last), (origin, destination, o.offer_id)


def test_a_real_flight_leaving_the_previous_local_day_is_a_candidate(tmp_path: Path) -> None:
    """Newark to London landing 07:00-10:00 London time: the overnight flight leaves the evening before."""
    value = requests_one("EWR", "LHR", "07:00", "10:00")
    key = solve_booking(value, tmp_path)
    assert key.trip.search_from == "2026-12-02"
    previous = [o for o in key.offers if o.offer_id in key.window_offer_ids and o.depart_local[:10] == "2026-12-02"]
    assert previous and key.refusal.value == "NONE"
    assert all(o.depart_local[11:] >= "16:00" for o in previous)


def test_a_departure_after_the_arrival_date_is_a_candidate_across_the_date_line() -> None:
    """Tokyo to Honolulu: a flight leaving Tokyo in the morning lands in Honolulu the evening before."""
    trip = make_trip(requests_one("NRT", "HNL", "18:00", "23:59"), "2026-11-05")
    assert day_number(trip.search_to) == day_number("2026-12-03") + 1


def requests_one(origin, destination, start, end):
    return request(origin=origin, destination=destination, arrive_from=start, arrive_to=end)


def test_the_booking_search_fits_the_hosted_context() -> None:
    largest = 0
    for origin, destination in routes(3):
        earliest, latest = window("2026-12-03", "00:00", "23:59", world.utc_offset(destination))
        first, last = search_days(earliest, latest, world.utc_offset(origin),
                                  world.journey_minutes(origin, destination), "2026-11-05")
        offers = world.offers_between(origin, destination, first, last)
        largest = max(largest, len(json.dumps([plain_output(offer) for offer in offers])))
    assert largest <= LARGEST_BOOKING_SEARCH_CHARS, largest
