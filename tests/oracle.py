"""An independent reading of the task instructions, written without the plugin's rules module (its own date
and time arithmetic with datetime, its own order of tests), to cross-check the answer key offer by offer.

It does not trust the trip's departure days: it reads every offer the simulated world sells on the route from
three days before the arrival date to two days after, keeps the ones sold (leaving today or later at the
origin, at most 330 days ahead) that land in the window, and so checks that the answer key misses none."""

from __future__ import annotations

from datetime import date, datetime, timedelta

from plugin import world


def utc(text: str) -> datetime:
    return datetime.fromisoformat(text)


def sold_offers(trip):
    """Every offer on the trip's route leaving 3 days before to 2 days after its arrival date and sold today."""
    arrival = date.fromisoformat(trip.arrival_date)
    today = date.fromisoformat(trip.booking_date)
    found = []
    for shift in range(-3, 3):
        day = arrival + timedelta(days=shift)
        if today <= day <= today + timedelta(days=330):
            number = (day - date(1970, 1, 1)).days
            found.extend(world.day_offers(trip.origin.code, trip.destination.code, number))
    return found


def booking_answer(trip, offers=None) -> tuple[str, bool, set[str]]:
    """(refusal, Senior VP approval required, the correct offer ids) among ``offers``, by default every offer
    sold on the route around the arrival date."""
    offers = sold_offers(trip) if offers is None else offers
    ahead = (date.fromisoformat(trip.arrival_date) - date.fromisoformat(trip.booking_date)).days
    required = ahead < 7
    if required and not trip.svp_approval:
        return "NO_SVP_APPROVAL", True, set()
    midnight = datetime.fromisoformat(trip.arrival_date) - timedelta(minutes=trip.destination.utc_offset_minutes)
    hour, minute = (int(part) for part in trip.arrive_from.split(":"))
    earliest = midnight + timedelta(hours=hour, minutes=minute - 90)
    hour, minute = (int(part) for part in trip.arrive_to.split(":"))
    latest = midnight + timedelta(hours=hour, minutes=minute + 90)
    landing = [offer for offer in offers if earliest <= utc(offer.segments[-1].arrive) <= latest]
    if not landing:
        return "NO_FLIGHT_IN_WINDOW", required, set()
    cheapest = min(offer.fare_cents for offer in landing)
    return "NONE", required, {offer.offer_id for offer in landing if offer.fare_cents == cheapest}
