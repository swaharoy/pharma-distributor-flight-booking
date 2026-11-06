"""Each tool's and task's typed input and output (see nanoagent.plugin.v0001.contract): declarations only."""

from dataclasses import dataclass
from enum import Enum
from typing import Annotated

from slimconfig import Output


class Tool(Enum):
    BOOKING_REQUIREMENTS = "booking_requirements"
    GET_TRIP = "get_trip"
    SEARCH_FLIGHTS = "search_flights"
    SOLVE_BOOKING = "solve_booking"


class Task(Enum):
    BOOKING_REQUIREMENTS = "booking-requirements"
    SEARCH_FLIGHTS = "search-flights"
    BOOK_FLIGHT = "pharma-distributor-flight-booking"


class AirportCode(Enum):
    """The airports this plugin knows, by IATA code (booking_requirements lists their names and cities)."""

    ATL = "ATL"
    LAX = "LAX"
    ORD = "ORD"
    DFW = "DFW"
    DEN = "DEN"
    JFK = "JFK"
    SFO = "SFO"
    SEA = "SEA"
    LAS = "LAS"
    MCO = "MCO"
    EWR = "EWR"
    MIA = "MIA"
    CLT = "CLT"
    PHX = "PHX"
    IAH = "IAH"
    BOS = "BOS"
    MSP = "MSP"
    DTW = "DTW"
    PHL = "PHL"
    LGA = "LGA"
    BWI = "BWI"
    SLC = "SLC"
    SAN = "SAN"
    IAD = "IAD"
    DCA = "DCA"
    TPA = "TPA"
    AUS = "AUS"
    BNA = "BNA"
    HNL = "HNL"
    ANC = "ANC"
    STL = "STL"
    YYZ = "YYZ"
    YVR = "YVR"
    YUL = "YUL"
    YHZ = "YHZ"
    MEX = "MEX"
    CUN = "CUN"
    LHR = "LHR"
    CDG = "CDG"
    FRA = "FRA"
    AMS = "AMS"
    MAD = "MAD"
    FCO = "FCO"
    MUC = "MUC"
    ZRH = "ZRH"
    DUB = "DUB"
    LIS = "LIS"
    CPH = "CPH"
    BCN = "BCN"
    VIE = "VIE"
    BRU = "BRU"
    OSL = "OSL"
    ARN = "ARN"
    KEF = "KEF"
    MAN = "MAN"
    EDI = "EDI"
    SNN = "SNN"
    NRT = "NRT"
    ICN = "ICN"
    SIN = "SIN"
    HKG = "HKG"
    DXB = "DXB"
    DEL = "DEL"
    BOM = "BOM"
    SYD = "SYD"
    GRU = "GRU"
    BOG = "BOG"
    JNB = "JNB"


class Cabin(Enum):
    ECONOMY = "ECONOMY"
    BUSINESS = "BUSINESS"
    FIRST = "FIRST"


class Refusal(Enum):
    NONE = "NONE"
    NO_SVP_APPROVAL = "NO_SVP_APPROVAL"
    NO_FLIGHT_IN_WINDOW = "NO_FLIGHT_IN_WINDOW"


class Topic(Enum):
    ALL = "ALL"
    FIELDS = "FIELDS"
    AIRPORTS = "AIRPORTS"


RUN_ID = "This booking run's id, as get_trip returned it"
TIME = "A UTC time, YYYY-MM-DD HH:MM"
CODE = "An IATA airport code, e.g. JFK"


@dataclass
class Airport(Output):
    code: Annotated[str, CODE]
    name: Annotated[str, "The airport's name"]
    city: Annotated[str, "The city it serves"]
    country: Annotated[str, "Its ISO 3166 country code, e.g. US"]
    utc_offset_minutes: Annotated[int, "Its standard-time offset from UTC in minutes, e.g. -300 for New York"]


@dataclass
class Trip(Output):
    traveller_name: Annotated[str, "The traveller's name"]
    origin: Annotated[Airport, "The airport the trip leaves from"]
    destination: Annotated[Airport, "The airport the trip goes to"]
    booking_date: Annotated[str, "Today, the day the ticket is requested, YYYY-MM-DD (UTC)"]
    arrival_date: Annotated[str, "The day the traveller must arrive, YYYY-MM-DD (local date at the destination)"]
    days_ahead: Annotated[int, "Days from booking_date to arrival_date"]
    arrive_from: Annotated[str, "The requested arrival window's start, HH:MM local time at the destination"]
    arrive_to: Annotated[str, "The requested arrival window's end, HH:MM local time at the destination"]
    window_earliest: Annotated[str, "arrive_from minus 90 minutes, as a UTC time YYYY-MM-DD HH:MM"]
    window_latest: Annotated[str, "arrive_to plus 90 minutes, as a UTC time YYYY-MM-DD HH:MM"]
    search_from: Annotated[str, "The first day a flight landing in the window can leave, YYYY-MM-DD (local date at "
                                "the origin, today or later)"]
    search_to: Annotated[str, "The last day a flight landing in the window can leave, YYYY-MM-DD (local date at "
                              "the origin)"]
    svp_approval: Annotated[bool, "Whether a Senior Vice President has approved this ticket"]


@dataclass
class Segment(Output):
    origin: Annotated[str, CODE]
    destination: Annotated[str, CODE]
    flight_number: Annotated[str, "The airline's flight number, e.g. DL 1482"]
    depart: Annotated[str, TIME]
    arrive: Annotated[str, TIME]
    air_minutes: Annotated[int, "Minutes in the air"]


@dataclass
class Offer(Output):
    offer_id: Annotated[str, "The offer's id: its departure date (local at the origin) and number, e.g. 20261203-04"]
    carrier: Annotated[str, "The airline"]
    cabin: Annotated[Cabin, "The cabin class"]
    fare_cents: Annotated[int, "The fare, in US cents"]
    refundable: Annotated[bool, "Whether the fare is refunded if the trip is cancelled"]
    change_fee_cents: Annotated[int, "The fee to change the flight, in US cents; 0 when changes are free"]
    total_air_minutes: Annotated[int, "Minutes in the air over all segments"]
    depart_local: Annotated[str, "When the first flight leaves, YYYY-MM-DD HH:MM local time at the origin"]
    arrive_local: Annotated[str, "When the last flight lands, YYYY-MM-DD HH:MM local time at the destination"]
    segments: Annotated[list[Segment], "The flights, in order"]


@dataclass
class TripInput(Output):
    traveller_name: Annotated[str, "The traveller's full name, as on the ticket"]
    origin: Annotated[AirportCode, "The airport to leave from, by IATA code (e.g. ORD for Chicago O'Hare)"]
    destination: Annotated[AirportCode, "The airport to fly to, by IATA code (e.g. BOS for Boston)"]
    arrival_date: Annotated[str, "The day the traveller must arrive, YYYY-MM-DD, today or later"]
    arrive_from: Annotated[str, "The earliest wanted arrival, HH:MM, 24-hour local time at the destination"]
    arrive_to: Annotated[str, "The latest wanted arrival, HH:MM, 24-hour local time at the destination"]
    svp_approval: Annotated[bool, "Whether a Senior Vice President has approved this ticket"]


@dataclass
class TripOutput(Output):
    run_id: Annotated[str, "This booking run's id: pass it to search_flights and submit it"]
    trip: Annotated[Trip, "The trip to book"]


@dataclass
class SearchInput(Output):
    run_id: Annotated[str, "This booking run's id, as get_trip returned it; empty to only look, outside a booking"]
    origin: Annotated[AirportCode, "The airport to leave from"]
    destination: Annotated[AirportCode, "The airport to fly to"]
    date_from: Annotated[str, "The first departure day to search, YYYY-MM-DD (local date at the origin), today or "
                              "later"]
    date_to: Annotated[str, "The last departure day to search, YYYY-MM-DD (local date at the origin), at most 7 "
                            "days after date_from"]


@dataclass
class SearchOutput(Output):
    run_id: Annotated[str, RUN_ID]
    note: Annotated[str, "Where the offers come from: simulated fares and schedules"]
    offers: Annotated[list[Offer], "Every one-way offer on the route leaving on the searched days, by departure"]


@dataclass
class BookingOutput(Output):
    run_id: Annotated[str, RUN_ID]
    booked: Annotated[bool, "Whether a flight is booked"]
    refusal: Annotated[Refusal, "Why nothing is booked; NONE when a flight is booked"]
    offer_id: Annotated[str, "The booked offer's id; empty when nothing is booked"]
    svp_approval_required: Annotated[bool, "Whether this ticket needs Senior Vice President approval"]


@dataclass
class SolveOutput(Output):
    pinned_at: Annotated[str, "When the answer key was pinned, UTC YYYY-MM-DD HH:MM:SS.ffffff"]
    trip: Annotated[Trip, "The trip, with today as its booking date"]
    offers: Annotated[list[Offer], "Every offer on the route leaving on the trip's days, search_from to search_to"]
    refusal: Annotated[Refusal, "The correct refusal, NONE when a flight must be booked"]
    svp_approval_required: Annotated[bool, "Whether the ticket needs Senior Vice President approval"]
    window_offer_ids: Annotated[list[str], "The offers arriving within the widened window"]
    lowest_fare_cents: Annotated[int, "The lowest fare in the window; 0 when nothing is booked"]
    correct_offer_ids: Annotated[list[str], "Every offer that is a correct booking"]


@dataclass
class RequirementsInput(Output):
    topic: Annotated[Topic, "ALL for everything, FIELDS for what to tell us, AIRPORTS for the airport list"]


@dataclass
class FieldHelp(Output):
    name: Annotated[str, "The field's name"]
    kind: Annotated[str, "What kind of value it takes"]
    required: Annotated[bool, "Whether every booking request must give it"]
    example: Annotated[str, "An example value"]
    description: Annotated[str, "What it means"]


@dataclass
class AirportHelp(Output):
    code: Annotated[str, CODE]
    name: Annotated[str, "The airport's name"]
    city: Annotated[str, "The city it serves"]
    country: Annotated[str, "Its ISO 3166 country code"]


@dataclass
class RequirementsOutput(Output):
    today: Annotated[str, "Today, the booking date, YYYY-MM-DD (UTC)"]
    fields: Annotated[list[FieldHelp], "What a booking request gives, field by field; empty for AIRPORTS"]
    date_rules: Annotated[list[str], "How the date and times work; empty for AIRPORTS"]
    airports: Annotated[list[AirportHelp], "The airports a trip may use; empty for FIELDS"]
    example_request: Annotated[str, "A complete booking request in plain words"]


TOOLS = {
    Tool.BOOKING_REQUIREMENTS: (RequirementsInput, RequirementsOutput),
    Tool.GET_TRIP: (TripInput, TripOutput),
    Tool.SEARCH_FLIGHTS: (SearchInput, SearchOutput),
    Tool.SOLVE_BOOKING: (TripInput, SolveOutput),
}
TASKS = {
    Task.BOOKING_REQUIREMENTS: (RequirementsInput, RequirementsOutput),
    Task.SEARCH_FLIGHTS: (SearchInput, SearchOutput),
    Task.BOOK_FLIGHT: (TripInput, BookingOutput),
}
