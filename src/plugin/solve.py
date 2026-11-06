"""solve_booking, the reference tool: the trip booked as of today, every offer leaving on its departure days
(search_from to search_to, every day whose flights can land in the arrival window) and the booking the rules
require, pinned before the agent starts and never shown to it."""

from pathlib import Path

from contract import SolveOutput, TripInput
from plugin import receipts, world
from plugin.rules import solve
from plugin.trip import make_trip


def solve_booking(value: TripInput, workspace: Path) -> SolveOutput:
    stamp = receipts.CLOCK()
    trip = make_trip(value, stamp[:10])
    offers = world.offers_between(trip.origin.code, trip.destination.code, trip.search_from, trip.search_to)
    answer = solve(trip, offers)
    return SolveOutput(
        pinned_at=stamp,
        trip=trip,
        offers=offers,
        refusal=answer.refusal,
        svp_approval_required=answer.approval_required,
        window_offer_ids=answer.in_window,
        lowest_fare_cents=answer.lowest_fare_cents,
        correct_offer_ids=answer.correct,
    )
