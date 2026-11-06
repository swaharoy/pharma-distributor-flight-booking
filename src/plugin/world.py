"""The simulated flight world, shared byte for byte by the tools (src/plugin/world.py) and the verifier
(verifier/world.py): real airports and real airline names, with synthetic schedules, fares and fare rules.

The offers on a route and departure day (the local date at the origin) come from a SHA-256 stream keyed by the
route and the day only, so the same search gives the same offers on every machine, on any booking date, and
the verifier can rebuild any search the agent made. Flights leave 06:00-21:55 local time at the origin; segment
times are UTC, and each offer also states its departure and arrival in local time. Nothing here is real fare or schedule data: airline names are used for realism
only. Every offer is an airline ticket sold through the corporate travel agency: no charters. It imports only
modules a verifier may use, contract, and the shared rules.
"""

import dataclasses
import hashlib
import math
from functools import cache
from itertools import pairwise

from contract import Airport, Cabin, Offer, Segment

from .rules import (
    FIRST_DEPARTURE,
    LAST_DEPARTURE,
    SEARCH_MAX_DAYS,
    date_of,
    day_number,
    local_text,
    minute_number,
    time_text,
)

NOTE = "Simulated fares and schedules; airline names are used for realism only."

# Airports: OurAirports (https://ourairports.com/data/, public domain), fetched 2026-11-02, trimmed to 68
# large airports. The last column is the airport's standard-time UTC offset in minutes (no daylight
# saving): it keeps departures in local daytime, states local times and turns a requested local arrival time
# into UTC.
# (code, name, city, country, continent, latitude, longitude, UTC offset in minutes)
AIRPORTS = (
    ('ATL', 'Hartsfield Jackson Atlanta International Airport', 'Atlanta', 'US', 'NA', 33.6367, -84.4281, -300),
    ('LAX', 'Los Angeles International Airport', 'Los Angeles', 'US', 'NA', 33.9425, -118.408, -480),
    ('ORD', "Chicago O'Hare International Airport", 'Chicago', 'US', 'NA', 41.9786, -87.9048, -360),
    ('DFW', 'Dallas Fort Worth International Airport', 'Dallas-Fort Worth', 'US', 'NA', 32.8968, -97.038, -360),
    ('DEN', 'Denver International Airport', 'Denver', 'US', 'NA', 39.86, -104.6738, -420),
    ('JFK', 'John F. Kennedy International Airport', 'New York', 'US', 'NA', 40.6394, -73.7793, -300),
    ('SFO', 'San Francisco International Airport', 'San Francisco', 'US', 'NA', 37.6198, -122.3748, -480),
    ('SEA', 'Seattle–Tacoma International Airport', 'Seattle', 'US', 'NA', 47.4479, -122.3103, -480),
    ('LAS', 'Harry Reid International Airport', 'Las Vegas', 'US', 'NA', 36.0834, -115.1518, -480),
    ('MCO', 'Orlando International Airport', 'Orlando', 'US', 'NA', 28.4294, -81.309, -300),
    ('EWR', 'Newark Liberty International Airport', 'Newark', 'US', 'NA', 40.6894, -74.1705, -300),
    ('MIA', 'Miami International Airport', 'Miami', 'US', 'NA', 25.796, -80.2898, -300),
    ('CLT', 'Charlotte Douglas International Airport', 'Charlotte', 'US', 'NA', 35.214, -80.9431, -300),
    ('PHX', 'Phoenix Sky Harbor International Airport', 'Phoenix', 'US', 'NA', 33.4353, -112.0059, -420),
    ('IAH', 'George Bush Intercontinental Airport', 'Houston', 'US', 'NA', 29.9844, -95.3414, -360),
    ('BOS', 'Boston Logan International Airport', 'Boston', 'US', 'NA', 42.362, -71.0079, -300),
    ('MSP', 'Minneapolis–Saint Paul International Airport / Wold–Chamberlain Field', 'Minneapolis', 'US', 'NA', 44.8801, -93.2217, -360),
    ('DTW', 'Detroit Metropolitan Wayne County Airport', 'Detroit', 'US', 'NA', 42.2138, -83.3538, -300),
    ('PHL', 'Philadelphia International Airport', 'Philadelphia', 'US', 'NA', 39.8719, -75.2411, -300),
    ('LGA', 'LaGuardia Airport', 'New York', 'US', 'NA', 40.7772, -73.8726, -300),
    ('BWI', 'Baltimore/Washington International Thurgood Marshall Airport', 'Baltimore', 'US', 'NA', 39.1754, -76.6683, -300),
    ('SLC', 'Salt Lake City International Airport', 'Salt Lake City', 'US', 'NA', 40.7889, -111.9799, -420),
    ('SAN', 'San Diego International Airport', 'San Diego', 'US', 'NA', 32.7336, -117.19, -480),
    ('IAD', 'Washington Dulles International Airport', 'Dulles', 'US', 'NA', 38.9445, -77.4558, -300),
    ('DCA', 'Ronald Reagan Washington National Airport', 'Washington', 'US', 'NA', 38.8521, -77.0377, -300),
    ('TPA', 'Tampa International Airport', 'Tampa', 'US', 'NA', 27.9755, -82.5332, -300),
    ('AUS', 'Austin Bergstrom International Airport', 'Austin', 'US', 'NA', 30.1975, -97.662, -360),
    ('BNA', 'Nashville International Airport', 'Nashville', 'US', 'NA', 36.1245, -86.6782, -360),
    ('HNL', 'Daniel K. Inouye International Airport', 'Honolulu, Oahu', 'US', 'OC', 21.3184, -157.9257, -600),
    ('ANC', 'Ted Stevens Anchorage International Airport', 'Anchorage', 'US', 'NA', 61.179, -149.9926, -540),
    ('STL', 'St. Louis Lambert International Airport', 'St Louis', 'US', 'NA', 38.7487, -90.37, -360),
    ('YYZ', 'Toronto Pearson International Airport', 'Toronto', 'CA', 'NA', 43.6759, -79.6294, -300),
    ('YVR', 'Vancouver International Airport', 'Vancouver', 'CA', 'NA', 49.1939, -123.184, -480),
    ('YUL', 'Montreal / Pierre Elliott Trudeau International Airport', 'Montréal', 'CA', 'NA', 45.4678, -73.7423, -300),
    ('YHZ', 'Halifax / Stanfield International Airport', 'Halifax', 'CA', 'NA', 44.8808, -63.5086, -240),
    ('MEX', 'Mexico City Benito Juárez International Airport', 'Mexico City', 'MX', 'NA', 19.4358, -99.0703, -360),
    ('CUN', 'Cancún International Airport', 'Cancún', 'MX', 'NA', 21.0408, -86.8735, -300),
    ('LHR', 'London Heathrow Airport', 'London', 'GB', 'EU', 51.4707, -0.4599, 0),
    ('CDG', 'Charles de Gaulle International Airport', "Paris (Roissy-en-France, Val-d'Oise)", 'FR', 'EU', 49.009, 2.5541, 60),
    ('FRA', 'Frankfurt Main Airport', 'Frankfurt am Main', 'DE', 'EU', 50.0267, 8.5584, 60),
    ('AMS', 'Amsterdam Airport Schiphol', 'Amsterdam', 'NL', 'EU', 52.3086, 4.7639, 60),
    ('MAD', 'Adolfo Suárez Madrid–Barajas Airport', 'Madrid', 'ES', 'EU', 40.4934, -3.5722, 60),
    ('FCO', 'Rome–Fiumicino Leonardo da Vinci International Airport', 'Rome', 'IT', 'EU', 41.8045, 12.252, 60),
    ('MUC', 'Munich Airport', 'Munich', 'DE', 'EU', 48.3538, 11.7861, 60),
    ('ZRH', 'Zürich Airport', 'Zurich', 'CH', 'EU', 47.4581, 8.5481, 60),
    ('DUB', 'Dublin Airport', 'Dublin', 'IE', 'EU', 53.4287, -6.2621, 0),
    ('LIS', 'Lisbon Humberto Delgado Airport', 'Lisbon', 'PT', 'EU', 38.7813, -9.1359, 0),
    ('CPH', 'Copenhagen Kastrup Airport', 'Copenhagen', 'DK', 'EU', 55.6179, 12.656, 60),
    ('BCN', 'Josep Tarradellas Barcelona-El Prat Airport', 'Barcelona', 'ES', 'EU', 41.2971, 2.0785, 60),
    ('VIE', 'Vienna International Airport', 'Vienna', 'AT', 'EU', 48.1103, 16.5697, 60),
    ('BRU', 'Brussels Airport', 'Zaventem', 'BE', 'EU', 50.9014, 4.4844, 60),
    ('OSL', 'Oslo-Gardermoen International Airport', 'Oslo (Gardermoen)', 'NO', 'EU', 60.1939, 11.1004, 60),
    ('ARN', 'Stockholm-Arlanda Airport', 'Stockholm', 'SE', 'EU', 59.6485, 17.9288, 60),
    ('KEF', 'Keflavik International Airport', 'Reykjavík', 'IS', 'EU', 63.985, -22.6056, 0),
    ('MAN', 'Manchester Airport', 'Manchester, Greater Manchester', 'GB', 'EU', 53.3494, -2.2795, 0),
    ('EDI', 'Edinburgh Airport', 'Ingliston, Edinburgh', 'GB', 'EU', 55.9501, -3.3723, 0),
    ('SNN', 'Shannon Airport', 'Shannon', 'IE', 'EU', 52.702, -8.9248, 0),
    ('NRT', 'Narita International Airport', 'Narita', 'JP', 'AS', 35.7686, 140.3887, 540),
    ('ICN', 'Incheon International Airport', 'Seoul', 'KR', 'AS', 37.4691, 126.451, 540),
    ('SIN', 'Singapore Changi Airport', 'Singapore', 'SG', 'AS', 1.3502, 103.994, 480),
    ('HKG', 'Hong Kong International Airport', 'Hong Kong', 'HK', 'AS', 22.3118, 113.9149, 480),
    ('DXB', 'Dubai International Airport', 'Dubai', 'AE', 'AS', 25.2498, 55.371, 240),
    ('DEL', 'Indira Gandhi International Airport', 'New Delhi', 'IN', 'AS', 28.5556, 77.0952, 330),
    ('BOM', 'Chhatrapati Shivaji Maharaj International Airport', 'Mumbai', 'IN', 'AS', 19.0887, 72.8679, 330),
    ('SYD', 'Sydney Kingsford Smith International Airport', 'Sydney (Mascot)', 'AU', 'OC', -33.9461, 151.177, 600),
    ('GRU', 'São Paulo/Guarulhos–Governor André Franco Montoro International Airport', 'São Paulo', 'BR', 'SA', -23.4313, -46.47, -180),
    ('BOG', 'El Dorado International Airport', 'Bogota', 'CO', 'SA', 4.7016, -74.1469, -300),
    ('JNB', 'O.R. Tambo International Airport', 'Johannesburg', 'ZA', 'AF', -26.1401, 28.2468, 120),
)

# Airlines: (IATA code, name, country, kind, longest nonstop in km, hubs and focus airports among AIRPORTS,
# cabins sold). kind: "us" (U.S. network airline), "low" (low-cost or leisure), "intl" (other network
# airline). Cabins: Y economy, J business, F first (for a U.S. airline, domestic first only).
AIRLINES = (
    ("DL", "Delta Air Lines", "US", "us", 15500, ("ATL", "DTW", "MSP", "SLC", "JFK", "LAX", "SEA", "BOS"), "YJF"),
    ("UA", "United Airlines", "US", "us", 15500, ("ORD", "DEN", "IAH", "EWR", "SFO", "IAD", "LAX"), "YJF"),
    ("AA", "American Airlines", "US", "us", 15000, ("DFW", "CLT", "ORD", "MIA", "PHL", "PHX", "JFK", "LAX", "DCA"), "YJF"),
    ("AS", "Alaska Airlines", "US", "low", 11000, ("SEA", "ANC", "SFO", "LAX", "HNL"), "YJ"),
    ("B6", "JetBlue", "US", "low", 5800, ("JFK", "BOS", "MCO"), "YJ"),
    ("WN", "Southwest Airlines", "US", "low", 4200, ("LAS", "DEN", "BWI", "PHX", "AUS", "BNA", "STL", "MCO", "TPA"), "Y"),
    ("AC", "Air Canada", "CA", "intl", 15000, ("YYZ", "YVR", "YUL"), "YJ"),
    ("AM", "Aeromexico", "MX", "intl", 12500, ("MEX",), "YJ"),
    ("BA", "British Airways", "GB", "intl", 15000, ("LHR",), "YJF"),
    ("VS", "Virgin Atlantic", "GB", "intl", 13000, ("LHR", "MAN"), "YJ"),
    ("AF", "Air France", "FR", "intl", 15000, ("CDG",), "YJF"),
    ("KL", "KLM", "NL", "intl", 15000, ("AMS",), "YJ"),
    ("LH", "Lufthansa", "DE", "intl", 15000, ("FRA", "MUC"), "YJF"),
    ("LX", "Swiss", "CH", "intl", 14000, ("ZRH",), "YJF"),
    ("IB", "Iberia", "ES", "intl", 13000, ("MAD",), "YJ"),
    ("EI", "Aer Lingus", "IE", "intl", 8000, ("DUB",), "YJ"),
    ("TP", "TAP Air Portugal", "PT", "intl", 12000, ("LIS",), "YJ"),
    ("SK", "SAS", "DK", "intl", 11000, ("CPH", "OSL", "ARN"), "YJ"),
    ("FI", "Icelandair", "IS", "low", 7500, ("KEF",), "YJ"),
    ("EK", "Emirates", "AE", "intl", 16000, ("DXB",), "YJF"),
    ("NH", "ANA", "JP", "intl", 15000, ("NRT",), "YJF"),
    ("KE", "Korean Air", "KR", "intl", 15000, ("ICN",), "YJF"),
    ("SQ", "Singapore Airlines", "SG", "intl", 16500, ("SIN",), "YJF"),
    ("CX", "Cathay Pacific", "HK", "intl", 15000, ("HKG",), "YJF"),
    ("AI", "Air India", "IN", "intl", 15500, ("DEL", "BOM"), "YJF"),
    ("QF", "Qantas", "AU", "intl", 15500, ("SYD",), "YJF"),
    ("LA", "LATAM", "BR", "intl", 12500, ("GRU",), "YJ"),
    ("AV", "Avianca", "CO", "intl", 9500, ("BOG",), "YJ"),
    ("SA", "South African Airways", "ZA", "intl", 13000, ("JNB",), "YJ"),
)

# Synthetic schedule and fare model. Every constant is a modelling choice, not real data.
CRUISE_KMH = 870  # block speed: minutes in the air = TAXI_MINUTES + distance at this speed
TAXI_MINUTES = 20
MIN_CONNECTION, MAX_CONNECTION = 45, 240  # minutes between flights at the hub (60 at least abroad)
MOST_ITINERARIES = 3  # itineraries flown on a route a day (a nonstop and connections)
MOST_NONSTOPS = 2
DETOUR = 1.35  # a connection flies at most this times the direct distance
SHORTEST_LEG_KM = 250
LONG_HAUL_KM = 2500
FLEX_PERCENT = 70  # the share of economy itineraries also sold as a refundable flexible fare
CHANGE_FEES = (0, 7_500, 10_000, 20_000)  # a non-refundable fare's fee to change the flight


def fare_base(km):
    """A one-way economy fare in cents for a nonstop of ``km``: $50 plus a concave per-distance part."""
    return 5_000 + round(30 * km ** 0.85)


class Rng:
    """A pseudo-random stream built on SHA-256: the same numbers on every machine and Python version."""

    def __init__(self, label):
        self.prefix = f"pharma-distributor-flight-booking:{label}:"
        self.count = 0

    def bits(self):
        digest = hashlib.sha256(f"{self.prefix}{self.count}".encode()).digest()
        self.count += 1
        return int.from_bytes(digest[:8], "big")

    def randint(self, low, high):
        """An integer from low to high, both included."""
        if high < low:
            raise ValueError(f"empty range {low}..{high}")
        return low + self.bits() % (high - low + 1)

    def choice(self, items):
        if not items:
            raise ValueError("choice from an empty sequence")
        return items[self.randint(0, len(items) - 1)]

    def chance(self, percent):
        return self.randint(1, 100) <= percent

    def shuffled(self, items):
        items = list(items)
        for index in range(len(items) - 1, 0, -1):
            other = self.randint(0, index)
            items[index], items[other] = items[other], items[index]
        return items


@cache
def airport_table():
    """{code: (code, name, city, country, continent, latitude, longitude, UTC offset)}"""
    return {row[0]: row for row in AIRPORTS}


@cache
def airline_table():
    return {row[0]: row for row in AIRLINES}


def is_airport(code):
    return code in airport_table()


def airport(code):
    row = airport_table().get(code)
    if row is None:
        raise ValueError(f"unknown airport {code!r}")
    return Airport(code=row[0], name=row[1], city=row[2], country=row[3], utc_offset_minutes=row[7])


def country(code):
    return airport_table()[code][3]


def utc_offset(code):
    return airport_table()[code][7]


@cache
def distance_km(origin, destination):
    """Great-circle distance between two airports, in whole km."""
    a, b = airport_table()[origin], airport_table()[destination]
    lat1, lon1, lat2, lon2 = (math.radians(value) for value in (a[5], a[6], b[5], b[6]))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return round(2 * 6371.0 * math.asin(math.sqrt(h)))


def air_minutes(origin, destination):
    """Minutes in the air for a nonstop flight: distance at block speed, plus taxi time."""
    return TAXI_MINUTES + round(distance_km(origin, destination) * 60 / CRUISE_KMH)


def leg_allowed(airline, origin, destination):
    """An airline may fly a leg within reach, and never one inside a country other than its own (cabotage)."""
    home, reach = airline[2], airline[4]
    if distance_km(origin, destination) > reach or distance_km(origin, destination) < SHORTEST_LEG_KM:
        return False
    return not (country(origin) == country(destination) != home)


@cache
def itineraries(origin, destination):
    """Every (airline code, airports flown through) an airline plausibly sells on a route: a nonstop when one
    end is its hub, and connections through its own hubs that add little distance."""
    direct = distance_km(origin, destination)
    found = []
    for airline in AIRLINES:
        code, hubs = airline[0], airline[5]
        if country(origin) == country(destination) != airline[2]:
            continue  # a domestic trip is sold by the country's own airlines only
        if (origin in hubs or destination in hubs) and leg_allowed(airline, origin, destination):
            found.append((code, (origin, destination)))
        if direct < 600:
            continue
        via = [
            hub for hub in hubs
            if hub not in (origin, destination)
            and leg_allowed(airline, origin, hub) and leg_allowed(airline, hub, destination)
            and distance_km(origin, hub) + distance_km(hub, destination) <= DETOUR * direct
        ]
        via.sort(key=lambda hub: (distance_km(origin, hub) + distance_km(hub, destination), hub))
        found.extend((code, (origin, hub, destination)) for hub in via[:2])
    return tuple(found)


def departure_minute(rng, code, day):
    """The UTC minute of a departure at 06:00-21:55 local time, in 5-minute steps, on ``day``, the local date at
    airport ``code``."""
    local = rng.randint(FIRST_DEPARTURE // 5, LAST_DEPARTURE // 5) * 5
    return day * 1440 + local - utc_offset(code)


def flight_number(code, origin, destination):
    """A stable flight number for an airline's leg, e.g. "DL 1482"."""
    digest = hashlib.sha256(f"flight:{code}:{origin}:{destination}".encode()).digest()
    return f"{code} {1 + int.from_bytes(digest[:4], 'big') % 2999}"


def is_long_haul(origin, destination):
    return distance_km(origin, destination) >= LONG_HAUL_KM


def connection_low(a, b):
    """The shortest connection after the leg a -> b: 60 minutes after an international leg, else 45."""
    return 60 if country(a) != country(b) else MIN_CONNECTION


@cache
def journey_minutes(origin, destination):
    """(shortest, longest) minutes from first departure to last arrival of any itinerary sold on the route, its
    connections at their shortest and longest; (0, 0) when no airline flies it."""
    spans = []
    for _code, path in itineraries(origin, destination):
        air = sum(air_minutes(a, b) for a, b in pairwise(path))
        lows = sum(connection_low(a, b) for a, b in pairwise(path[:-1]))
        spans.append((air + lows, air + MAX_CONNECTION * (len(path) - 2)))
    if not spans:
        return 0, 0
    return min(span[0] for span in spans), max(span[1] for span in spans)


def build_segments(rng, airline_code, path, day):
    first = departure_minute(Rng(f"time:{airline_code}:{'-'.join(path)}"), path[0], day)
    segments = []
    start = first
    for index in range(len(path) - 1):
        a, b = path[index], path[index + 1]
        air = air_minutes(a, b)
        segments.append(Segment(
            origin=a, destination=b, flight_number=flight_number(airline_code, a, b),
            depart=time_text(start), arrive=time_text(start + air), air_minutes=air,
        ))
        start += air + rng.randint(connection_low(a, b) // 5, MAX_CONNECTION // 5) * 5
    return segments


def day_drafts(origin, destination, day):
    """The day's offers before numbering: (first departure, fare, cabin, carrier, refundable, change fee,
    segments). Each itinerary sells a non-refundable economy fare, often a dearer refundable one too, and
    business or first where its airline sells them."""
    rng = Rng(f"day:{origin}:{destination}:{day}")
    options = itineraries(origin, destination)
    nonstops = [option for option in options if len(option[1]) == 2 and rng.chance(95)]
    connections = [option for option in options if len(option[1]) == 3 and rng.chance(75)]
    chosen = rng.shuffled(nonstops)[:MOST_NONSTOPS]
    chosen += rng.shuffled(connections)[: MOST_ITINERARIES - len(chosen)]
    direct = distance_km(origin, destination)
    international = country(origin) != country(destination)
    long_haul = is_long_haul(origin, destination)
    drafts = []
    for airline_code, path in chosen:
        airline = airline_table()[airline_code]
        kind = airline[3]
        economy = fare_base(direct) * rng.randint(80, 135) // 100
        if len(path) == 3:
            economy = economy * rng.randint(78, 95) // 100
        if kind == "low":
            economy = economy * 88 // 100
        drafts.append((Cabin.ECONOMY, economy, airline, path, False, rng.choice(CHANGE_FEES)))
        if rng.chance(FLEX_PERCENT):
            drafts.append((Cabin.ECONOMY, economy * rng.randint(135, 220) // 100, airline, path, True, 0))
        cabins = airline[6]
        if "J" in cabins and (kind != "low" or long_haul):
            business = (
                (international and (long_haul or kind == "intl"))
                or (direct >= 3_500 and rng.chance(60))
            )
            if business and rng.chance(85):
                times = rng.randint(140, 190) if rng.chance(12) else rng.randint(300, 500)
                if not long_haul:
                    times = rng.randint(180, 300)
                if rng.chance(8):
                    times = rng.randint(85, 99)  # a business sale below the economy fare
                drafts.append((Cabin.BUSINESS, economy * times // 100, airline, path, rng.chance(60), 0))
        if "F" in cabins and kind == "us" and not international and direct < 3_500 and rng.chance(70):
            drafts.append((Cabin.FIRST, economy * rng.randint(180, 260) // 100, airline, path, True, 0))
        if "F" in cabins and long_haul and kind == "intl" and rng.chance(35):
            drafts.append((Cabin.FIRST, economy * rng.randint(600, 900) // 100, airline, path, True, 0))
    built = []
    for cabin, fare, airline, path, refundable, change_fee in drafts:
        segments = build_segments(Rng(f"segments:{origin}:{destination}:{day}:{airline[0]}:{'-'.join(path)}"),
                                  airline[0], path, day)
        built.append((segments[0].depart, fare, cabin.value, airline[1], cabin, refundable, change_fee, segments))
    return built


def day_offers(origin, destination, day):
    """Every offer on a route leaving on day number ``day`` (the local date at the origin), in departure order,
    numbered <date>-01, ...
    Fresh copies on each call, so no caller can change another's offers."""
    return tuple(
        dataclasses.replace(offer, segments=[dataclasses.replace(segment) for segment in offer.segments])
        for offer in built_day(origin, destination, day)
    )


@cache
def built_day(origin, destination, day):
    if not is_airport(origin) or not is_airport(destination):
        raise ValueError(f"unknown route {origin!r} -> {destination!r}")
    if origin == destination:
        raise ValueError("origin and destination are the same airport")
    drafts = sorted(day_drafts(origin, destination, day), key=lambda d: (d[0], d[1], d[2], d[3], d[5]))
    stamp = date_of(day).replace("-", "")
    origin_offset, destination_offset = utc_offset(origin), utc_offset(destination)
    return tuple(
        Offer(
            offer_id=f"{stamp}-{index:02d}",
            carrier=carrier,
            cabin=cabin,
            fare_cents=fare,
            refundable=refundable,
            change_fee_cents=change_fee,
            total_air_minutes=sum(segment.air_minutes for segment in segments),
            depart_local=local_text(minute_number(segments[0].depart), origin_offset),
            arrive_local=local_text(minute_number(segments[-1].arrive), destination_offset),
            segments=segments,
        )
        for index, (_, fare, _, carrier, cabin, refundable, change_fee, segments) in enumerate(drafts, start=1)
    )


def offers_between(origin, destination, date_from, date_to):
    """Every offer on a route leaving on a day from date_from to date_to (local dates at the origin, at most
    SEARCH_MAX_DAYS apart)."""
    first, last = day_number(date_from), day_number(date_to)
    if not 0 <= last - first <= SEARCH_MAX_DAYS:
        raise ValueError(f"date_to must be 0 to {SEARCH_MAX_DAYS} days after date_from")
    offers = []
    for day in range(first, last + 1):
        offers.extend(day_offers(origin, destination, day))
    return offers
