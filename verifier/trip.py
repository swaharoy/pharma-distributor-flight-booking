"""get_trip's checks: a request that can be booked, the trip it states, and the run it began."""

from .checks import RUN_ID, read_json, result
from .rules import booking_date_problem, request_plain, request_problem, trip_matches_request
from .world import airport, journey_minutes


def verify_input(value):
    problem = request_problem(value)
    return result(problem is None, problem or "a well-formed trip request")


def verify_output(input_value, output_value, workspace):
    trip = output_value.trip
    if trip.origin != airport(trip.origin.code) or trip.destination != airport(trip.destination.code):
        return result(False, "the trip's airports are not the airport list's")
    if not trip_matches_request(trip, input_value, journey_minutes(trip.origin.code, trip.destination.code)):
        return result(False, "the trip is not the one the request asked for, with its window, days ahead and "
                      "departure days")
    problem = booking_date_problem(trip.arrival_date, trip.booking_date)
    if problem:
        return result(False, problem)
    if not RUN_ID.fullmatch(output_value.run_id):
        return result(False, f"run_id {output_value.run_id!r} is not a run id")
    receipt = read_json(f"{workspace}/runs/{output_value.run_id}/trip.json")
    if (
        receipt is None
        or receipt.get("request") != request_plain(input_value)
        or receipt.get("booking_date") != trip.booking_date
    ):
        return result(False, f"run {output_value.run_id} has no receipt for this request in the workspace")
    return result(True, f"the trip of the request, booked {trip.booking_date}, run {output_value.run_id}")
