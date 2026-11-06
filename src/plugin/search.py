"""search_flights: the one-way offers on a route, leaving on the searched days (local dates at the origin)."""

from pathlib import Path

from contract import SearchInput, SearchOutput
from plugin import receipts, world
from plugin.rules import SEARCH_MAX_DAYS, booking_date_problem, day_number, offers_digest


def search_flights(value: SearchInput, workspace: Path) -> SearchOutput:
    if value.origin is value.destination:
        raise ValueError("origin and destination are the same airport")
    span = day_number(value.date_to) - day_number(value.date_from)
    if not 0 <= span <= SEARCH_MAX_DAYS:
        raise ValueError(f"date_to must be 0 to {SEARCH_MAX_DAYS} days after date_from")
    # In a booking run, today is the run's booking date; a search outside a run (run_id empty) is only shown.
    folder, started = receipts.run_trip(workspace, value.run_id) if value.run_id else (None, None)
    today = started["booking_date"] if started else receipts.CLOCK()[:10]
    problem = booking_date_problem(value.date_from, today) or booking_date_problem(value.date_to, today)
    if problem:
        raise ValueError(problem)
    offers = world.offers_between(value.origin.value, value.destination.value, value.date_from, value.date_to)
    if folder is not None:
        receipts.add_search(
            folder,
            {
                "origin": value.origin.value,
                "destination": value.destination.value,
                "date_from": value.date_from,
                "date_to": value.date_to,
                "offer_ids": [offer.offer_id for offer in offers],
                "digest": offers_digest(offers),
            },
        )
    return SearchOutput(run_id=value.run_id, note=world.NOTE, offers=offers)
