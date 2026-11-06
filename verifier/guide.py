"""What a booking request must give, shared byte for byte by the booking_requirements tool
(src/plugin/guide.py) and the verifier (verifier/guide.py): every field of the booking task's input, read
from the contract, with an example; the date and time rules; and the airports. No policy: applying the policy
is the agent's job, not the traveller's. It imports only modules a verifier may use, contract, and its
package's shared modules.
"""

import dataclasses
import enum
import typing

from contract import AirportCode, AirportHelp, FieldHelp, RequirementsOutput, Topic, TripInput

from .rules import BOOKING_HORIZON_DAYS, date_of, day_number
from .world import AIRPORTS

EXAMPLE_ARRIVAL_DAYS = 30  # the example request arrives this many days after today


def example_date(today):
    return date_of(day_number(today) + EXAMPLE_ARRIVAL_DAYS)


def examples(today):
    return {
        "traveller_name": "Maya Chen",
        "origin": "ORD",
        "destination": "BOS",
        "arrival_date": example_date(today),
        "arrive_from": "13:00",
        "arrive_to": "17:00",
        "svp_approval": "false",
    }


def kind_of(name, kind):
    """What kind of value a field takes, in words."""
    if kind is bool:
        return "yes or no (true or false)"
    if isinstance(kind, type) and issubclass(kind, AirportCode):
        return f"an airport code from the airport list ({len(AIRPORTS)} airports)"
    if isinstance(kind, type) and issubclass(kind, enum.Enum):
        return "one of " + ", ".join(member.value for member in kind)
    if name.endswith("_date"):
        return "a date, YYYY-MM-DD"
    if name.startswith("arrive_"):
        return "a time of day, HH:MM (24-hour, local time at the destination)"
    return "text"


def fields(today):
    """Every field of the booking task's input, in the contract's order."""
    hints = typing.get_type_hints(TripInput, include_extras=True)
    example = examples(today)
    found = []
    for field in dataclasses.fields(TripInput):
        kind, description = typing.get_args(hints[field.name])
        found.append(FieldHelp(name=field.name, kind=kind_of(field.name, kind), required=True,
                               example=example[field.name], description=description))
    return found


def date_rules(today):
    last = date_of(day_number(today) + BOOKING_HORIZON_DAYS)
    return [
        f"Today is {today} (UTC): a request made today is booked as of today.",
        (
            "The arrival date is the day you must land, YYYY-MM-DD, local date at the destination; the flight "
            "may leave a day or two earlier (overnight or long-haul) or, across the date line, a day later."
        ),
        (
            "Give the arrival window as two 24-hour times, HH:MM, in local standard time at the destination: "
            "the earliest and the latest you want to land (the same time twice for one exact time)."
        ),
        (
            f"Flights are sold from today up to {BOOKING_HORIZON_DAYS} days ahead: the arrival date is {today} or "
            f"later, and {last} or earlier."
        ),
    ]


def airports():
    return [AirportHelp(code=row[0], name=row[1], city=row[2], country=row[3]) for row in AIRPORTS]


def example_request(today):
    return (
        f"Book a flight for Maya Chen from Chicago O'Hare (ORD) to Boston (BOS), arriving on {example_date(today)} "
        "between 13:00 and 17:00 Boston time; she has no Senior Vice President approval."
    )


def build(topic, today):
    """The requirements for ``topic`` as of ``today``."""
    wants_fields = topic in (Topic.ALL, Topic.FIELDS)
    wants_airports = topic in (Topic.ALL, Topic.AIRPORTS)
    return RequirementsOutput(
        today=today,
        fields=fields(today) if wants_fields else [],
        date_rules=date_rules(today) if wants_fields else [],
        airports=airports() if wants_airports else [],
        example_request=example_request(today),
    )
