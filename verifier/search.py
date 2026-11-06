"""search_flights' checks: a well-formed query, and exactly the simulated world's offers for it."""

from .checks import RUN_ID, result
from .rules import SEARCH_MAX_DAYS, day_number, is_date, same_offers
from .world import NOTE, offers_between


def verify_input(value):
    if value.origin is value.destination:
        return result(False, f"origin and destination are both {value.origin.value}")
    for name, date in (("date_from", value.date_from), ("date_to", value.date_to)):
        if not is_date(date):
            return result(False, f"{name} {date!r} is not a real YYYY-MM-DD date")
    span = day_number(value.date_to) - day_number(value.date_from)
    if not 0 <= span <= SEARCH_MAX_DAYS:
        return result(False, f"date_to must be 0 to {SEARCH_MAX_DAYS} days after date_from")
    if value.run_id and not RUN_ID.fullmatch(value.run_id):
        return result(False, f"run_id {value.run_id!r} is not one get_trip returned")
    return result(True, "a well-formed search")


def verify_output(input_value, output_value, workspace):
    q = input_value
    if output_value.run_id != q.run_id:
        return result(False, "the result names another run")
    if output_value.note != NOTE:
        return result(False, "the result does not say its fares and schedules are simulated")
    expected = offers_between(q.origin.value, q.destination.value, q.date_from, q.date_to)
    if not same_offers(output_value.offers, expected):
        return result(False, "the offers are not the route's offers on the searched days")
    return result(True, f"{len(expected)} offers on {q.origin.value}-{q.destination.value}, {q.date_from} to {q.date_to}")
