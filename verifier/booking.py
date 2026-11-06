"""The pharma-distributor-flight-booking verdict: named checks, in order, on the answer key, the run the
submission names, its search receipts, and the booking against rules M1-M5.

Every search receipt is checked against the simulated world rebuilt here (verifier/world.py, the tools' own
file), so any offer the agent saw, on any day it searched, is known exactly.

The first five checks are integrity gates; the rest are the policy. The verdict is valid, scoring 1, only
when every check holds; any failure, gate or policy, scores 0: a booking follows the policy or it does not. A
check that depends on a failed one is "not checked". Expected values come from the verifier's own copy of the
rules applied to the pinned trip and offers; the answer key's own booking is checked to agree with them.
"""

from contract import Refusal

from .checks import check, result, run_files
from .rules import (
    APPROVAL_DAYS,
    WINDOW_MINUTES,
    arrival_minute,
    departure_date,
    in_departure_days,
    in_window,
    minute_number,
    offers_digest,
    request_plain,
    solve,
)
from .solve import answer_key_problem
from .world import offers_between

TEXT = {
    "answer-key": "The answer key pinned this request's trip, booked today, its offers, and a booking that follows the rules",
    "this-run": "The submission names a run get_trip began for this request on the same booking date, after the answer key",
    "searched": "The agent searched for flights in this run (not needed to refuse for lack of Senior VP approval)",
    "receipts-match": "Every search in this run returned exactly the route's offers for its query",
    "offer-seen": "The booked offer was among this run's search results, on the trip's route",
    "approval": "M2: svp_approval_required is true exactly when the arrival date is fewer than 7 days after booking",
    "refusal": "M2/M5: book unless Senior VP approval is needed and missing, or no flight lands in the window",
    "window": "M3: the flight lands from 90 minutes before to 90 minutes after the window (leaving on any day it can)",
    "fare": "M4: the lowest fare in the window, whatever its cabin, refundability or change fee",
}
GATES = ("answer-key", "this-run", "searched", "receipts-match", "offer-seen")
POLICY = ("approval", "refusal", "window", "fare")


def money(cents):
    return f"${cents // 100}.{cents % 100:02d}"


class Verdict:
    def __init__(self):
        self.entries = {}
        self.blocked_by = None

    def add(self, check_id, ok, expected="", actual="", message=""):
        if self.blocked_by is not None:
            self.entries[check_id] = check(
                check_id, TEXT[check_id], None, message=f"not checked: {self.blocked_by} failed"
            )
            return
        self.entries[check_id] = check(check_id, TEXT[check_id], ok, expected, actual, message)
        if not ok:
            self.blocked_by = check_id

    def finish(self):
        entries = [self.entries[check_id] for check_id in GATES + POLICY]
        failed = [entry for entry in entries if entry["ok"] is False]
        if not failed:
            return result(True, "valid: the booking follows every rule", score=1.0, checks=entries)
        first = failed[0]
        return result(False, f"{first['id']}: {first['message']}", score=0.0, checks=entries)


def verify_task(arguments, output, reference, workspace):
    verdict = Verdict()
    # Gate 1: the answer key.
    problem = "no answer key was pinned" if reference is None else answer_key_problem(arguments, reference)
    route = f"{arguments.origin.value}-{arguments.destination.value} arriving {arguments.arrival_date}"
    verdict.add("answer-key", problem is None, f"the key of {route}", "none" if reference is None else
                f"booked {reference.trip.booking_date}", problem or "the answer key is this request's and follows the rules")
    if problem is not None:
        for check_id in GATES[1:] + POLICY:
            verdict.add(check_id, None)
        return verdict.finish()
    trip, offers = reference.trip, reference.offers
    answer = solve(trip, offers)

    # Gate 2: this run.
    started, searches = run_files(workspace, output.run_id)
    if not isinstance(started, dict) or started.get("request") != request_plain(arguments):
        verdict.add("this-run", False, "a run of this request", output.run_id,
                    f"the workspace holds no run {output.run_id!r} begun by get_trip for this request")
    elif started.get("booking_date") != trip.booking_date:
        verdict.add("this-run", False, f"booked {trip.booking_date}", str(started.get("booking_date")),
                    f"run {output.run_id} was booked on another day than the answer key")
    elif not isinstance(started.get("started_at"), str) or started["started_at"] < reference.pinned_at:
        verdict.add("this-run", False, f"begun after {reference.pinned_at}", str(started.get("started_at")),
                    f"run {output.run_id} began before this task's answer key: it is an earlier run")
    else:
        verdict.add("this-run", True, actual=output.run_id, message=f"run {output.run_id} began at {started['started_at']}")

    # Gate 3: searched (a refusal for lack of Senior VP approval does not depend on the flights).
    needs_search = not (output.booked is False and output.refusal is Refusal.NO_SVP_APPROVAL)
    if needs_search and not searches:
        verdict.add("searched", False, "at least one search_flights call", "none",
                    "the agent booked or refused without calling search_flights in this run")
    else:
        verdict.add("searched", True, actual=f"{len(searches)} searches", message="searched" if searches else
                    "a refusal for lack of Senior VP approval needs no search")

    # Gate 4: every search receipt matches the simulated world's offers for its query.
    seen = {}
    mismatch = None
    for number, receipt in enumerate(searches, start=1):
        if not isinstance(receipt, dict):
            mismatch = f"search {number}'s receipt is unreadable"
            break
        try:
            expected = offers_between(receipt["origin"], receipt["destination"], receipt["date_from"],
                                      receipt["date_to"])
        except (KeyError, TypeError, ValueError):
            mismatch = f"search {number}'s receipt is malformed"
            break
        if receipt.get("offer_ids") != [o.offer_id for o in expected] or receipt.get("digest") != offers_digest(expected):
            mismatch = f"search {number} returned offers other than the route's offers for its query"
            break
        seen.update({o.offer_id: o for o in expected})
    verdict.add("receipts-match", mismatch is None, "receipts equal to the route's offers", mismatch or "equal",
                mismatch or f"{len(searches)} search receipts match the simulated offers")

    # Gate 5: the booked offer was seen, on the trip's route.
    route = f"{trip.origin.code}-{trip.destination.code}"
    if output.booked and output.offer_id not in seen:
        verdict.add("offer-seen", False, "an offer id from this run's search results", output.offer_id,
                    f"offer {output.offer_id!r} was not among this run's search results")
    elif output.booked:
        flown = seen[output.offer_id]
        flies = f"{flown.segments[0].origin}-{flown.segments[-1].destination}"
        verdict.add("offer-seen", flies == route, f"an offer on {route}", f"{output.offer_id} on {flies}",
                    f"offer {output.offer_id} was in the search results" if flies == route else
                    f"offer {output.offer_id} flies {flies}, not the trip's route {route}")
    else:
        verdict.add("offer-seen", True, message="nothing booked")

    # M2: the approval flag.
    days = trip.days_ahead
    verdict.add("approval", output.svp_approval_required is answer.approval_required, answer.approval_required,
                output.svp_approval_required,
                f"the trip arrives {days} days after booking on {trip.booking_date}: Senior VP approval is "
                + ("required (under 7 days)" if answer.approval_required else f"not required ({APPROVAL_DAYS} or more days)"))

    # M2/M5: booking or refusal.
    want = answer.refusal
    shape_problem = None
    if output.booked and output.refusal is not Refusal.NONE:
        shape_problem = f"booked is true but refusal is {output.refusal.value}: a booking has refusal NONE"
    elif not output.booked and output.refusal is Refusal.NONE:
        shape_problem = "nothing is booked but refusal is NONE: give the reason"
    elif not output.booked and output.offer_id:
        shape_problem = "nothing is booked: offer_id must be empty"
    got = "booked" if output.booked else f"not booked ({output.refusal.value})"
    expected = "booked" if want is Refusal.NONE else f"not booked ({want.value})"
    if shape_problem:
        verdict.add("refusal", False, expected, got, shape_problem)
    else:
        verdict.add("refusal", got == expected, expected, got, refusal_reason(trip, want))
    if not output.booked or verdict.blocked_by is not None:
        message = "nothing is booked" if verdict.blocked_by is None else None
        for check_id in POLICY[2:]:
            if message:
                verdict.add(check_id, True, message=f"not applicable: {message}")
            else:
                verdict.add(check_id, None)
        return verdict.finish()

    offer = seen[output.offer_id]
    oid = offer.offer_id
    # M3
    window = f"{trip.window_earliest} to {trip.window_latest} UTC"
    lands = offer.segments[-1].arrive
    if not in_departure_days(trip, offer):
        verdict.add("window", False, f"leaves {trip.search_from} to {trip.search_to}", departure_date(offer),
                    f"offer {oid} leaves {departure_date(offer)}, outside the trip's departure days "
                    f"{trip.search_from} to {trip.search_to}")
    elif not in_window(trip, offer):
        verdict.add("window", False, window, lands,
                    f"offer {oid} lands {lands} UTC ({offer.arrive_local} local), outside {trip.arrive_from}-"
                    f"{trip.arrive_to} local time widened by {WINDOW_MINUTES} minutes ({window}); {gap(trip, offer)}")
    else:
        verdict.add("window", True, window, lands,
                    f"offer {oid} lands {lands} UTC ({offer.arrive_local} local), inside the window")
    # M4
    verdict.add("fare", offer.fare_cents == answer.lowest_fare_cents, money(answer.lowest_fare_cents),
                money(offer.fare_cents),
                f"offer {oid} costs {money(offer.fare_cents)}; the lowest fare landing in the window is "
                f"{money(answer.lowest_fare_cents)} (cabin, refundability and change fees do not count)")
    return verdict.finish()


def gap(trip, offer):
    """How far outside the window an offer lands."""
    landed = arrival_minute(offer)
    low, high = minute_number(trip.window_earliest), minute_number(trip.window_latest)
    if landed < low:
        return f"{low - landed} minutes early"
    return f"{landed - high} minutes late"


def refusal_reason(trip, want):
    if want is Refusal.NO_SVP_APPROVAL:
        return (f"the trip arrives {trip.days_ahead} days after booking, under {APPROVAL_DAYS}, and no Senior VP "
                "approval is held: the ticket cannot be issued")
    if want is Refusal.NO_FLIGHT_IN_WINDOW:
        return (f"no flight leaving from {trip.search_from} to {trip.search_to} (every day that can reach it) lands "
                "within the widened window")
    return "a flight lands in the window and the ticket may be issued: book it"
