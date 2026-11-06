"""solve_booking's checks: the pinned trip is the request's, its offers are the simulated world's, and its
answer is what the rules give for them."""

from .checks import result
from .rules import booking_date_problem, request_problem, same_offers, solve, trip_matches_request
from .world import airport, journey_minutes, offers_between


def verify_input(value):
    problem = request_problem(value)
    return result(problem is None, problem or "a well-formed trip request")


def verify_output(input_value, output_value, workspace):
    problem = answer_key_problem(input_value, output_value)
    return result(problem is None, problem or "the answer key follows the rules")


def answer_key_problem(request, key):
    """What is wrong with a pinned answer key for ``request``, or None."""
    problem = request_problem(request)
    if problem:
        return f"the request is malformed: {problem}"
    trip = key.trip
    if trip.origin != airport(trip.origin.code) or trip.destination != airport(trip.destination.code):
        return "the answer key's airports are not the airport list's"
    if not trip_matches_request(trip, request, journey_minutes(trip.origin.code, trip.destination.code)):
        return "the answer key's trip is not the one the request asked for"
    if not key.pinned_at.startswith(trip.booking_date + " "):
        return "the answer key's booking date is not the day it was pinned"
    problem = booking_date_problem(trip.arrival_date, trip.booking_date)
    if problem:
        return f"the answer key's trip cannot be booked: {problem}"
    if not same_offers(key.offers, offers_between(trip.origin.code, trip.destination.code, trip.search_from,
                                                  trip.search_to)):
        return "the answer key's offers are not the route's offers on the trip's departure days"
    answer = solve(trip, key.offers)
    pinned = (key.refusal, key.svp_approval_required, key.window_offer_ids, key.lowest_fare_cents,
              key.correct_offer_ids)
    computed = (answer.refusal, answer.approval_required, answer.in_window, answer.lowest_fare_cents, answer.correct)
    if pinned != computed:
        return "the answer key's booking is not what the rules give for its trip and offers"
    return None
