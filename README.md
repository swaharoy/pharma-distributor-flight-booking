# Pharma Distributor Flight Booking

A NanoAgent plugin (`nanoagent.plugin/v0001`): a traveller says where they fly from and to and when they need
to land, an agent books one one-way flight for them under a pharmaceutical distributor's corporate travel
policy, as of today, acting as the company's travel agency, and a deterministic verifier checks the booking
against every rule.

The policy is based on the **2006 McKesson Corporate Travel Policy**, §I.A Air Travel, filed with the SEC as
exhibit 10.17 (<https://www.sec.gov/Archives/edgar/data/1468328/000119312509181308/dex1017.htm>). This plugin
is **unofficial**: it is not made, endorsed or used by McKesson, and it restates the policy as exact rules of
its own (below).

**Simulated fares and schedules.** Airports and airline names are real; every flight, fare, fare rule and
schedule is synthetic, made by the plugin (see *The simulated flights* below). Airline names are used for
realism only: nothing here is a real fare or a real timetable.

## Tools

| Tool | Does | Code |
|---|---|---|
| `booking_requirements` | What a booking request must give, field by field with examples (read from the contract), the date and time rules, the airports to choose from, and an example request, as of today. Nothing about the policy: applying it is the agent's job | `src/plugin/requirements.py`, `src/plugin/guide.py` |
| `get_trip` | Begins a booking run for a trip request: the trip as booked today (traveller, airports with their UTC offsets, booking date, arrival date, days ahead, the requested arrival window in local time and widened by 90 minutes in UTC, the departure days `search_from` to `search_to` whose flights can land in it, Senior VP approval held) and its `run_id` | `src/plugin/trip.py` |
| `search_flights` | The one-way offers on a route leaving on the searched days (local dates at the origin, at most 7 days apart, today or later): airline, flight numbers, cabin, fare, refundability, change fee, segment times in UTC, and departure and arrival in local time (`depart_local`, `arrive_local`) | `src/plugin/search.py` |
| `solve_booking` | The answer key: the trip as booked today, every offer leaving on its departure days and the booking the rules require. NanoAgent runs it before the agent, out of its sight; it is never one of the agent's tools | `src/plugin/solve.py` |

### Tasks

| Task | Does | Runner |
|---|---|---|
| `booking-requirements` | Shows what to tell us to book a flight (topic `ALL`, `FIELDS` or `AIRPORTS`) | `tool`, with `booking_requirements` |
| `search-flights` | Shows the offers on a route and days | `tool`, with `search_flights` |
| `pharma-distributor-flight-booking` | Books a flight for a trip request under the policy | `agent`, with `get_trip` and `search_flights`; reference `solve_booking` |

The booking task's input is the trip request, which the chat fills from plain words such as "book Maya Chen
from Chicago O'Hare to Boston, landing on Dec 3 between 1 and 5 pm Boston time, no SVP approval":
`traveller_name`, `origin` and `destination` (airport codes from the list), `arrival_date`, `arrive_from`
and `arrive_to` (24-hour `HH:MM`, local standard time at the destination) and `svp_approval`. The booking date
is today (UTC), read when the answer key is pinned; requests arriving before today or more than 330 days
ahead are refused.

The agent's path is three tool calls: `get_trip` with the request, `search_flights` from the trip's
`search_from` to its `search_to`, then `submit` (a short-notice trip without approval needs no search).
`get_trip` works the departure days out: every local date at the origin from which a flight sold on the route
(leaving 06:00-21:55 local, taking its shortest to longest journey) could land in the widened window, from
today on. That is one to three days, often the day before the arrival date for overnight and long-haul
flights, and the day after across the date line; the largest such search on any route is 29 offers
(15,031 characters of JSON). It submits `run_id`, `booked`, `refusal`
(`NONE`, `NO_SVP_APPROVAL` or `NO_FLIGHT_IN_WINDOW`), `offer_id` and `svp_approval_required`.

### The rules (the task's instructions state them exactly)

| Rule | Policy text it formalises | Exact rule |
|---|---|---|
| M1 | "All travel arrangements … must be arranged through McKesson's currently designated corporate travel agency" | The agent acts as the agency; there is no other channel |
| M2 | "Any tickets being requested within 7-days of travel require Senior V.P. approval before the ticket can be issued" | `svp_approval_required` is true exactly when the arrival date is fewer than 7 days after booking (exactly 7 is not within); then, without approval, refusal `NO_SVP_APPROVAL` |
| M3 | "The Agency will check all flights one and a half hours before and one and a half hours after the originally requested arrival" | Every flight landing from `arrive_from` − 90 minutes to `arrive_to` + 90 minutes, local time on the arrival date, both ends included, whatever day it leaves (the trip's departure days hold every one); connections allowed |
| M4 | "The lowest available airfare, regardless of penalties or restriction, must be utilized" | The lowest fare among them, whatever its cabin, refundability or change fee; tied fares all pass |
| M5 | — | No flight passes M3: refusal `NO_FLIGHT_IN_WINDOW` (M2 is checked first) |

Out of scope: the "business needs dictated by a customer" exception (the agent only minimises price), the
agency's step of advising the traveller of fare options, every non-air rule, round trips, and daylight saving
time (local times use each airport's standard
time).

### The simulated flights

`src/plugin/world.py` (the same file as `verifier/world.py`) makes the offers on a route and departure day
(the local date at the origin) from a SHA-256 stream keyed by the route and the day only, so a search gives the
same offers on every machine and on any booking date, and the verifier rebuilds every search the agent made. Its model, every constant of which is
a modelling choice, not data:

- **Airports:** 68 large airports from OurAirports (public domain), fetched 2026-11-02, with their
  standard-time UTC offsets. Segment times are UTC; every flight leaves between 06:00 and 21:55 local time
  at its origin on its day, on every continent.
- **Airlines:** 29 real airlines, each with its country, hubs among the 68 airports, longest nonstop and cabins
  sold. An airline sells a nonstop when one end is its hub, and connections through its own hubs that add at
  most 35% distance; a domestic trip is sold only by that country's airlines, and no airline flies a leg
  inside another country. Up to three itineraries fly a route each day; flight numbers (e.g. `DL 1482`) are
  stable per airline and leg. No charters: every offer is an airline ticket the agency can issue.
- **Times:** minutes in the air are 20 + the great-circle distance at 870 km/h; connections take 45 to 240
  minutes (60 at least between countries).
- **Fares:** economy is $50 + 30 x km^0.85 cents, times 0.80-1.35 by day, connections 78-95% of that, and
  low-cost airlines 88%. Each itinerary sells a non-refundable economy fare with a change fee of $0, $75, $100
  or $200, and on 70% of them a refundable economy fare at 1.35-2.2x with free changes. Business is 3-5x
  economy on long haul (sometimes a 1.4-1.9x sale, now and then a sale just below economy) and 1.8-3x on short
  flights; U.S. airlines sell domestic first at 1.8-2.6x; some long-haul airlines sell first at 6-9x.

Exact boundaries (landing exactly 90 minutes outside the window, exactly 7 days ahead, tied fares) rarely occur
in realistic data, so the tests and scripted cases check them with hand-built offers, which replace the world
in the tools and the verifier alike.

## Layout

It has the standard plugin layout, which NanoAgent requires:

```text
.
├── nanoagent.yaml   # manifest: id, runtime, permissions (no network), tools, tasks and their instructions
├── contract.py      # each tool's and task's typed input and output: slimconfig Output classes
├── README.md
├── LICENSE
├── pyproject.toml
├── uv.lock
├── .gitignore
├── .env             # needed environment variable names (none)
├── src/plugin/      # the MCP server (__main__.py, IMPLEMENTATIONS) and the tools
│   ├── world.py     # airports, airlines and the simulated offers; the same file as verifier/world.py
│   ├── rules.py     # requests, dates, times and rules M2-M5 as exact integer code; the same file as verifier/rules.py
│   ├── guide.py     # what a booking request must give; the same file as verifier/guide.py
│   └── receipts.py  # each run's receipts in the workspace: runs/<run id>/trip.json, search-<n>.json
├── tests/           # rules, world, requirements, verifier, scripted cases (tests/cases/*.json), MCP server
├── ui/              # renderers.js / renderers.css: the requirements, the offers table, the booking
├── product/         # product.yaml and icon.svg
└── verifier/        # the deterministic verifier: one module per tool and booking.py for the task
```

The verdict of the booking task is a list of named checks, each with `ok`, `expected`, `actual` and a message
naming the offer and the rule:

- integrity gates: `answer-key` (the pinned key is this request's, booked on the day it was pinned, with the
  route's offers, and follows the rules), `this-run` (the submitted run was begun by `get_trip` for this
  request, on the same booking date, after the key was pinned), `searched` (not needed to refuse for lack of
  approval), `receipts-match` (every search receipt equals the route's offers for its query, rebuilt by the
  verifier), `offer-seen` (the booked offer was in this run's search results, on the trip's route);
- policy: `approval`, `refusal`, `window`, `fare`.

The verdict is valid, scoring 1, only when every check holds; any failed check scores 0, since a booking
either follows the policy or it does not. Checks after a failed one they depend on are "not checked". Expected
values come from the verifier's own copy of the rules applied to the pinned trip and offers.

## Develop and run

```bash
uv sync --extra dev
uv run pytest
uv run ruff check .
```

The tests freeze today at 2026-11-05, so they pass on any day. `uv run pytest` replays the scripted cases in
`tests/cases/` (gold, wrong, missing, malformed, tampered and boundary runs) through the real tools and
verifier, checks the answer key against an independent reading of the rules for 400 varied requests, and
checks the simulated world's plausibility, determinism and size.

NanoAgent passes the folder the plugin may write to as `NANOAGENT_WORKSPACE`; the tools write only their
receipts there, under `runs/`. To check the plugin with NanoAgent from its checkout:

```bash
uv run nanoagent plugin inspect <path to this plugin>
```
