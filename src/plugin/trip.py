"""get_trip: the trip a request describes, booked as of today, with its arrival window in UTC and the departure
days whose flights can land in it, and a new run to book it in."""

from pathlib import Path

from contract import Trip, TripInput, TripOutput
from plugin import receipts, world
from plugin.rules import (
    booking_date_problem,
    day_number,
    request_plain,
    request_problem,
    search_days,
    time_text,
    window,
)


def make_trip(value: TripInput, booking_date: str) -> Trip:
    """The trip of a request on ``booking_date``; raises when the request cannot be booked that day."""
    problem = request_problem(value) or booking_date_problem(value.arrival_date, booking_date)
    if problem:
        raise ValueError(problem)
    origin, destination = world.airport(value.origin.value), world.airport(value.destination.value)
    earliest, latest = window(value.arrival_date, value.arrive_from, value.arrive_to, destination.utc_offset_minutes)
    search_from, search_to = search_days(earliest, latest, origin.utc_offset_minutes,
                                         world.journey_minutes(origin.code, destination.code), booking_date)
    return Trip(
        traveller_name=value.traveller_name,
        origin=origin,
        destination=destination,
        booking_date=booking_date,
        arrival_date=value.arrival_date,
        days_ahead=day_number(value.arrival_date) - day_number(booking_date),
        arrive_from=value.arrive_from,
        arrive_to=value.arrive_to,
        window_earliest=time_text(earliest),
        window_latest=time_text(latest),
        search_from=search_from,
        search_to=search_to,
        svp_approval=value.svp_approval,
    )


def get_trip(value: TripInput, workspace: Path) -> TripOutput:
    stamp = receipts.CLOCK()
    trip = make_trip(value, stamp[:10])
    run_id = receipts.new_run(workspace, request_plain(value), trip.booking_date, stamp)
    return TripOutput(run_id=run_id, trip=trip)
