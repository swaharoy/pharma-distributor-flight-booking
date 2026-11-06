"""The pharmaceutical distributor's air-travel rules, shared byte for byte by the tools (src/plugin/rules.py)
and the verifier (verifier/rules.py): dates and times, what a trip request may be, the arrival window, the
departure days whose flights can land in it, which offers the policy allows, the booking it requires, and the
canonical form of requests and offers both sides compare.

Exact integer arithmetic only, and no datetime (a verifier may not import it): a date is a day number and a
time a minute number. It imports only modules a verifier may use, and contract.
"""

import hashlib
import json
import re
from dataclasses import dataclass

from contract import Refusal

DATE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
TIME = re.compile(r"^(\d{4}-\d{2}-\d{2}) (\d{2}):(\d{2})$")
CLOCK_TIME = re.compile(r"^(\d{2}):(\d{2})$")
APPROVAL_DAYS = 7  # a ticket for travel within 7 days needs Senior VP approval (exactly 7 days ahead does not)
WINDOW_MINUTES = 90  # the agency checks flights 1.5 hours before and after the requested arrival
SEARCH_MAX_DAYS = 7  # one search covers at most this many days after date_from
BOOKING_HORIZON_DAYS = 330  # flights are sold up to this many days after today
NAME_MOST_CHARS = 80
FIRST_DEPARTURE = 6 * 60  # flights leave from 06:00 local time at the origin ...
LAST_DEPARTURE = 22 * 60 - 5  # ... to 21:55, in 5-minute steps


def day_number(date):
    """Days since 1970-01-01 of a YYYY-MM-DD date; ValueError when it is not a real date."""
    match = DATE.fullmatch(date)
    if not match:
        raise ValueError(f"{date!r} is not a YYYY-MM-DD date")
    year, month, day = (int(part) for part in match.groups())
    if not 1 <= month <= 12 or not 1 <= day <= days_in_month(year, month):
        raise ValueError(f"{date!r} is not a real date")
    year -= month <= 2
    era = year // 400
    year_of_era = year - era * 400
    day_of_year = (153 * (month + (-3 if month > 2 else 9)) + 2) // 5 + day - 1
    day_of_era = year_of_era * 365 + year_of_era // 4 - year_of_era // 100 + day_of_year
    return era * 146097 + day_of_era - 719468


def date_of(number):
    """The YYYY-MM-DD date of a day number."""
    number += 719468
    era = number // 146097
    day_of_era = number - era * 146097
    year_of_era = (day_of_era - day_of_era // 1460 + day_of_era // 36524 - day_of_era // 146096) // 365
    day_of_year = day_of_era - (365 * year_of_era + year_of_era // 4 - year_of_era // 100)
    shifted = (5 * day_of_year + 2) // 153
    day = day_of_year - (153 * shifted + 2) // 5 + 1
    month = shifted + (3 if shifted < 10 else -9)
    year = year_of_era + era * 400 + (month <= 2)
    return f"{year:04d}-{month:02d}-{day:02d}"


def days_in_month(year, month):
    if month == 2:
        return 29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28
    return 30 if month in (4, 6, 9, 11) else 31


def is_date(text):
    try:
        day_number(text)
    except ValueError:
        return False
    return True


def minute_number(time):
    """Minutes since 1970-01-01 00:00 of a YYYY-MM-DD HH:MM time; ValueError when it is not one."""
    match = TIME.fullmatch(time)
    if not match:
        raise ValueError(f"{time!r} is not a YYYY-MM-DD HH:MM time")
    date, hour, minute = match.group(1), int(match.group(2)), int(match.group(3))
    if hour > 23 or minute > 59:
        raise ValueError(f"{time!r} is not a real time")
    return day_number(date) * 1440 + hour * 60 + minute


def clock_minutes(text):
    """Minutes after midnight of an HH:MM time of day; ValueError when it is not one."""
    match = CLOCK_TIME.fullmatch(text)
    if not match:
        raise ValueError(f"{text!r} is not an HH:MM time")
    hour, minute = int(match.group(1)), int(match.group(2))
    if hour > 23 or minute > 59:
        raise ValueError(f"{text!r} is not a real time of day")
    return hour * 60 + minute


def is_clock_time(text):
    try:
        clock_minutes(text)
    except ValueError:
        return False
    return True


def time_text(minute):
    """YYYY-MM-DD HH:MM of a minute number (minutes since 1970-01-01 00:00 UTC)."""
    return f"{date_of(minute // 1440)} {minute % 1440 // 60:02d}:{minute % 60:02d}"


def local_text(minute, utc_offset_minutes):
    """YYYY-MM-DD HH:MM local time of a UTC minute number at an airport ``utc_offset_minutes`` from UTC."""
    return time_text(minute + utc_offset_minutes)


def request_problem(request):
    """What is wrong with a trip request on its own (no clock needed), or None."""
    if not request.traveller_name.strip():
        return "traveller_name is blank: give the traveller's name"
    if len(request.traveller_name) > NAME_MOST_CHARS:
        return f"traveller_name is longer than {NAME_MOST_CHARS} characters"
    if request.origin is request.destination:
        return f"origin and destination are both {request.origin.value}: give two different airports"
    if not is_date(request.arrival_date):
        return f"arrival_date {request.arrival_date!r} is not a real YYYY-MM-DD date"
    for name, value in (("arrive_from", request.arrive_from), ("arrive_to", request.arrive_to)):
        if not is_clock_time(value):
            return f"{name} {value!r} is not a 24-hour HH:MM time"
    if clock_minutes(request.arrive_to) < clock_minutes(request.arrive_from):
        return f"arrive_to {request.arrive_to} is before arrive_from {request.arrive_from}"
    return None


def booking_date_problem(date, booking_date):
    """What is wrong with travelling on ``date`` when booked on ``booking_date`` (today), or None."""
    if day_number(date) < day_number(booking_date):
        return f"{date} is before today, {booking_date}: flights cannot leave in the past"
    if day_number(date) > day_number(booking_date) + BOOKING_HORIZON_DAYS:
        return (f"{date} is more than {BOOKING_HORIZON_DAYS} days after today, {booking_date}: "
                "flights are not sold that far ahead")
    return None


def window(arrival_date, arrive_from, arrive_to, utc_offset_minutes):
    """M3: the widened arrival window as UTC minute numbers, both ends included: arrive_from - 90 minutes to
    arrive_to + 90 minutes, local time at the destination on arrival_date."""
    midnight = day_number(arrival_date) * 1440 - utc_offset_minutes
    return (midnight + clock_minutes(arrive_from) - WINDOW_MINUTES,
            midnight + clock_minutes(arrive_to) + WINDOW_MINUTES)


def search_days(earliest, latest, origin_offset_minutes, journey, booking_date):
    """The departure days (local dates at the origin, YYYY-MM-DD) whose flights can land from UTC minute
    ``earliest`` to ``latest``: a flight leaves 06:00-21:55 local time and takes ``journey`` = (shortest,
    longest) minutes from first departure to last arrival on the route. Days before today or more than 330
    days ahead are not sold and are left out; when no sold day can reach the window, the one nearest it."""
    shortest, longest = journey
    first = -((longest + LAST_DEPARTURE - origin_offset_minutes - earliest) // 1440)  # ceiling division
    last = (latest - shortest - FIRST_DEPARTURE + origin_offset_minutes) // 1440
    low, high = day_number(booking_date), day_number(booking_date) + BOOKING_HORIZON_DAYS
    first = min(max(first, low), high)
    last = min(max(last, first), high)
    return date_of(first), date_of(last)


def request_plain(request):
    """A trip request as plain JSON values, the form receipts record and the verifier compares."""
    return {
        "traveller_name": request.traveller_name,
        "origin": request.origin.value,
        "destination": request.destination.value,
        "arrival_date": request.arrival_date,
        "arrive_from": request.arrive_from,
        "arrive_to": request.arrive_to,
        "svp_approval": request.svp_approval,
    }


def trip_matches_request(trip, request, journey):
    """Whether a trip states exactly what the request asked for, with its window, days ahead and departure
    days worked out (``journey``: the route's shortest and longest journey in minutes)."""
    earliest, latest = window(request.arrival_date, request.arrive_from, request.arrive_to,
                              trip.destination.utc_offset_minutes)
    days = None
    if is_date(trip.booking_date):
        days = search_days(earliest, latest, trip.origin.utc_offset_minutes, journey, trip.booking_date)
    return (
        trip.traveller_name == request.traveller_name
        and trip.origin.code == request.origin.value
        and trip.destination.code == request.destination.value
        and trip.arrival_date == request.arrival_date
        and trip.arrive_from == request.arrive_from
        and trip.arrive_to == request.arrive_to
        and trip.svp_approval is request.svp_approval
        and is_date(trip.booking_date)
        and trip.days_ahead == day_number(trip.arrival_date) - day_number(trip.booking_date)
        and trip.window_earliest == time_text(earliest)
        and trip.window_latest == time_text(latest)
        and (trip.search_from, trip.search_to) == days
    )


def departure_date(offer):
    """The day an offer departs: the local date at the origin of its first segment's departure."""
    return offer.depart_local[:10]


def arrival_minute(offer):
    """When an offer lands at the destination: its last segment's arrival, as a UTC minute number."""
    return minute_number(offer.segments[-1].arrive)


def approval_required(trip):
    """M2: a ticket for travel fewer than 7 days after it is requested needs Senior VP approval (days counted
    to the arrival date)."""
    return trip.days_ahead < APPROVAL_DAYS


def in_departure_days(trip, offer):
    """Whether an offer leaves on one of the trip's departure days, search_from to search_to."""
    return day_number(trip.search_from) <= day_number(departure_date(offer)) <= day_number(trip.search_to)


def in_window(trip, offer):
    """M3: leaves on one of the trip's departure days (the days whose flights can land in the window) and lands
    within the widened window, both ends included."""
    if not in_departure_days(trip, offer):
        return False
    return minute_number(trip.window_earliest) <= arrival_minute(offer) <= minute_number(trip.window_latest)


@dataclass
class Answer:
    """The booking the rules require for a trip and its offers."""

    refusal: Refusal
    approval_required: bool
    in_window: list  # offer ids arriving within the widened window
    lowest_fare_cents: int
    correct: list  # offer ids that are correct bookings


def solve(trip, offers):
    """The rules applied in order: M2 Senior VP approval, M3 the arrival window, M4 the lowest fare whatever its
    cabin and restrictions, M5 nothing in the window. M1 (the agent acts as the agency) is the task itself."""
    required = approval_required(trip)
    if required and not trip.svp_approval:
        return Answer(Refusal.NO_SVP_APPROVAL, required, [], 0, [])
    inside = [offer for offer in offers if in_window(trip, offer)]
    if not inside:
        return Answer(Refusal.NO_FLIGHT_IN_WINDOW, required, [], 0, [])
    lowest = min(offer.fare_cents for offer in inside)
    return Answer(
        Refusal.NONE,
        required,
        [offer.offer_id for offer in inside],
        lowest,
        [offer.offer_id for offer in inside if offer.fare_cents == lowest],
    )


def offer_plain(offer):
    """An offer as plain JSON values, the form both sides hash."""
    return {
        "offer_id": offer.offer_id,
        "carrier": offer.carrier,
        "cabin": offer.cabin.value,
        "fare_cents": offer.fare_cents,
        "refundable": offer.refundable,
        "change_fee_cents": offer.change_fee_cents,
        "total_air_minutes": offer.total_air_minutes,
        "depart_local": offer.depart_local,
        "arrive_local": offer.arrive_local,
        "segments": [
            {
                "origin": segment.origin,
                "destination": segment.destination,
                "flight_number": segment.flight_number,
                "depart": segment.depart,
                "arrive": segment.arrive,
                "air_minutes": segment.air_minutes,
            }
            for segment in offer.segments
        ],
    }


def offers_digest(offers):
    """The SHA-256 of a list of offers in their canonical JSON form."""
    text = json.dumps([offer_plain(offer) for offer in offers], sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def same_offers(left, right):
    """Whether two lists of offers are the same offers, in the same order."""
    return [offer_plain(offer) for offer in left] == [offer_plain(offer) for offer in right]
