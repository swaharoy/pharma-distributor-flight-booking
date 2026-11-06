"""Building values the way NanoAgent's sandbox does, and running the tools and verifier like the host."""

from __future__ import annotations

import hashlib
from contextlib import contextmanager
from pathlib import Path

from slimconfig import build_output, plain_output

import verifier
import verifier.world
from contract import TASKS, TOOLS, AirportCode, Offer, SearchInput, SolveOutput, Task, Tool, TripInput
from plugin import get_trip, search_flights, solve_booking, world
from plugin.rules import date_of, day_number, local_text, minute_number

BOOK = Task.BOOK_FLIGHT.value
CODES = [member.value for member in AirportCode]


def request(**changes) -> TripInput:
    """A trip request: by default Chicago O'Hare to Boston, arriving 2026-12-03 between 13:00 and 17:00 Boston
    time, without Senior VP approval."""
    value = {
        "traveller_name": "Maya Chen", "origin": "ORD", "destination": "BOS", "arrival_date": "2026-12-03",
        "arrive_from": "13:00", "arrive_to": "17:00", "svp_approval": False,
    } | changes
    return build_output(value, TripInput)


def requests(count: int, salt: str = "requests"):
    """``count`` varied trip requests, chosen by SHA-256 so they are the same on every machine: any route,
    arriving 0 to 60 days after today, in a window of 0 to 8 hours from 05:00 to 23:00, approval held or not."""
    for index in range(count):
        digest = hashlib.sha256(f"{salt}:{index}".encode()).digest()
        origin = CODES[digest[0] % len(CODES)]
        destination = CODES[digest[1] % len(CODES)]
        if origin == destination:
            continue
        arrival = day_number("2026-11-05") + digest[2] % 60
        start = 5 * 60 + digest[3] % 64 * 15
        end = min(23 * 60 + 59, start + digest[4] % 33 * 15)
        yield request(origin=origin, destination=destination, arrival_date=date_of(arrival),
                      arrive_from=f"{start // 60:02d}:{start % 60:02d}", arrive_to=f"{end // 60:02d}:{end % 60:02d}",
                      svp_approval=bool(digest[5] % 3 == 0))


def booking(run_id: str, offer_id: str = "", *, booked: bool = True, refusal: str = "NONE",
            required: bool = False) -> dict:
    return {"run_id": run_id, "booked": booked, "refusal": refusal, "offer_id": offer_id,
            "svp_approval_required": required}


def judge(arguments: TripInput, output: dict, reference: SolveOutput | None, workspace: Path) -> dict:
    """verify_task on plain values built into their contract classes, as the sandbox does."""
    given, made = TASKS[Task.BOOK_FLIGHT]
    key = None if reference is None else build_output(plain_output(reference), SolveOutput)
    return verifier.verify_task(BOOK, build_output(plain_output(arguments), given), build_output(output, made), key,
                                str(workspace))


class Run:
    """One booking run: the answer key pinned in a scratch folder, then get_trip and a search in the workspace."""

    def __init__(self, value: TripInput, root: Path, *, search: bool = True) -> None:
        self.request = value
        self.workspace = root / "workspace"
        self.workspace.mkdir(parents=True, exist_ok=True)
        scratch = root / "scratch"
        scratch.mkdir(parents=True, exist_ok=True)
        self.key = solve_booking(value, scratch)
        started = get_trip(value, self.workspace)
        self.run_id = started.run_id
        self.trip = started.trip
        self.offers = []
        if search:
            self.offers = self.search().offers

    def search(self, date_from: str | None = None, date_to: str | None = None, *, origin=None, destination=None):
        trip = self.trip
        return search_flights(
            SearchInput(self.run_id, AirportCode(origin or trip.origin.code),
                        AirportCode(destination or trip.destination.code), date_from or trip.search_from,
                        date_to or trip.search_to),
            self.workspace,
        )

    def gold(self) -> dict:
        key = self.key
        required = key.svp_approval_required
        if key.refusal.value != "NONE":
            return booking(self.run_id, booked=False, refusal=key.refusal.value, required=required)
        return booking(self.run_id, key.correct_offer_ids[0], required=required)

    def book(self, offer_id: str) -> dict:
        return booking(self.run_id, offer_id, required=self.key.svp_approval_required)

    def judge(self, output: dict) -> dict:
        return judge(self.request, output, self.key, self.workspace)


def failed(verdict: dict) -> list[str]:
    return [entry["id"] for entry in verdict["details"]["checks"] if entry["ok"] is False]


def tool_input(tool: str, value: dict) -> dict:
    return verifier.verify_input(tool, build_output(value, TOOLS[Tool(tool)][0]))


@contextmanager
def hand_built(offers: dict[str, list[dict]], origin: str = "ORD", destination: str = "BOS"):
    """The world replaced, in the tools and the verifier alike, by hand-built offers: {date: [plain offers]}
    (the local departure date at the origin) on one route, and no offers on any other route or day. Used for
    exact boundaries real fares rarely hit."""
    days = {day_number(date): tuple(build_output(offer, Offer) for offer in day) for date, day in offers.items()}

    def day_offers(o, d, day):
        return days.get(day, ()) if (o, d) == (origin, destination) else ()

    saved = world.day_offers, verifier.world.day_offers
    world.day_offers = verifier.world.day_offers = day_offers
    try:
        yield
    finally:
        world.day_offers, verifier.world.day_offers = saved


def offer(offer_id: str, fare: int, *, arrive: str = "2026-12-03 20:00", cabin: str = "ECONOMY",
          refundable: bool = False, change_fee: int = 0, minutes: tuple = (125,), origin: str = "ORD",
          destination: str = "BOS", carrier: str = "United Airlines") -> dict:
    """A plain hand-built offer landing at ``arrive`` (UTC): nonstop, or through a hub when ``minutes`` has two
    values (an hour's connection). Its local times use the airports' UTC offsets."""
    points = [origin, *["DTW"] * (len(minutes) - 1), destination]
    end = minute_number(arrive)
    start = end - sum(minutes) - 60 * (len(minutes) - 1)
    depart_local = local_text(start, world.utc_offset(origin))
    segments = []
    for index, air in enumerate(minutes):
        segments.append({
            "origin": points[index], "destination": points[index + 1], "flight_number": f"UA {100 + index}",
            "depart": world.time_text(start), "arrive": world.time_text(start + air), "air_minutes": air,
        })
        start += air + 60
    return {"offer_id": offer_id, "carrier": carrier, "cabin": cabin, "fare_cents": fare, "refundable": refundable,
            "change_fee_cents": change_fee, "total_air_minutes": sum(minutes), "depart_local": depart_local,
            "arrive_local": local_text(end, world.utc_offset(destination)), "segments": segments}
