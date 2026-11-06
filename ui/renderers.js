// How this plugin's page draws its tasks' outputs: what to tell us to book (fields, date and time rules,
// airports), the flight offers as a table, and a booking as the chosen offer or the reason nothing was booked.
import { dataTable, disclosure, h, plural, statusPill } from "./kit/components.js";

const money = (cents) => `$${(cents / 100).toFixed(2)}`;

function facts(rows) {
  return h(
    "dl",
    { class: "trip-facts" },
    rows.map(([label, value]) => [h("dt", { text: label }), h("dd", { text: value })]),
  );
}

function fieldsTable(fields) {
  return dataTable({
    columns: [
      { key: "name", label: "Field", primary: true },
      { key: "kind", label: "Takes" },
      { key: "example", label: "Example" },
      { key: "description", label: "Meaning" },
    ],
    rows: fields,
    caption: "What to tell us",
    empty: "No fields.",
  }).element;
}

function airportsTable(airports) {
  return dataTable({
    columns: [
      { key: "code", label: "Code", primary: true },
      { key: "city", label: "City" },
      { key: "country", label: "Country" },
      { key: "name", label: "Airport" },
    ],
    rows: airports,
    sort: { key: "code" },
    caption: "Airports",
    empty: "No airports.",
  }).element;
}

function requirements(answer) {
  const parts = [h("p", { class: "muted", text: `Booking as of today, ${answer.today}` })];
  if (answer.fields.length) parts.push(fieldsTable(answer.fields));
  if (answer.date_rules.length) {
    parts.push(h("h4", { text: "Date and times" }), h("ul", { class: "rules" }, answer.date_rules.map((rule) => h("li", { text: rule }))));
  }
  parts.push(h("h4", { text: "For example" }), h("blockquote", { class: "example", text: answer.example_request }));
  if (answer.airports.length) {
    parts.push(disclosure({ summary: plural(answer.airports.length, "airport"), open: !answer.fields.length }, airportsTable(answer.airports)));
  }
  return h("div", { class: "requirements" }, parts);
}

function route(offer) {
  const stops = offer.segments.map((segment) => segment.origin).concat(offer.segments.at(-1).destination);
  return stops.join(" → ");
}

function offersTable(offers) {
  return dataTable({
    columns: [
      { key: "offer_id", label: "Offer", primary: true },
      { key: "depart", label: "Departs (UTC)", value: (o) => o.segments[0].depart },
      { key: "arrive", label: "Arrives (UTC)", value: (o) => o.segments.at(-1).arrive },
      { key: "depart_local", label: "Departs (local)" },
      { key: "arrive_local", label: "Arrives (local)" },
      { key: "route", label: "Route", value: route },
      { key: "carrier", label: "Airline" },
      { key: "flights", label: "Flights", value: (o) => o.segments.map((s) => s.flight_number).join(", ") },
      { key: "cabin", label: "Cabin", value: (o) => o.cabin.toLowerCase() },
      { key: "fare_cents", label: "Fare", numeric: true, render: (o) => money(o.fare_cents) },
      { key: "refundable", label: "Refundable", value: (o) => (o.refundable ? "yes" : "no") },
      { key: "change_fee_cents", label: "Change fee", numeric: true, render: (o) => money(o.change_fee_cents) },
      { key: "total_air_minutes", label: "Air min", numeric: true },
    ],
    rows: offers,
    sort: { key: "depart" },
    caption: "Flight offers",
    empty: "No offers on this route and these days.",
  }).element;
}

export default {
  RequirementsOutput: requirements,
  SearchOutput: ({ note, offers }) =>
    h(
      "div",
      { class: "offers" },
      h("p", { class: "muted", text: `${plural(offers.length, "offer")}. ${note}` }),
      offersTable(offers),
    ),
  BookingOutput: (booking) =>
    booking.booked
      ? h(
          "div",
          { class: "booking" },
          statusPill(`Booked ${booking.offer_id}`, "ok", { icon: true }),
          facts([
            ["Senior VP approval", booking.svp_approval_required ? "required (held)" : "not required"],
            ["Run", booking.run_id],
          ]),
        )
      : h(
          "div",
          { class: "booking" },
          statusPill("Not booked", "warn", { icon: true }),
          facts([
            [
              "Reason",
              booking.refusal === "NO_SVP_APPROVAL"
                ? "Travel within 7 days needs Senior Vice President approval"
                : "No flight lands in the arrival window",
            ],
            ["Senior VP approval", booking.svp_approval_required ? "required" : "not required"],
            ["Run", booking.run_id],
          ]),
        ),
};
