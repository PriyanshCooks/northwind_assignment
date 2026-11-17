// Display helpers only. The server sends figures already rounded to 2 decimals; nothing here recalculates one.
const GBP = new Intl.NumberFormat("en-GB", { style: "currency", currency: "GBP", minimumFractionDigits: 2, maximumFractionDigits: 2 });
const PLAIN = new Intl.NumberFormat("en-GB", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const FIGURE_NAMES = {
  group_revenue: "Group revenue", group_profit: "Group profit for the year", profit_owners: "Profit attributable to owners",
  profit_nci: "Profit attributable to non-controlling interest", nci_closing: "Non-controlling interest, closing",
  goodwill_closing: "Goodwill, closing", translation_reserve_movement: "Translation reserve movement",
  total_assets: "Total assets", total_equity: "Total equity", intercompany_difference: "Intercompany difference",
  sgd_bank_gbp: "Singapore dollar bank balance in GBP", journals: "Adjusting journals",
};

// Money arrives as text ("1234567.50"). Intl.NumberFormat reads a numeric string exactly, so it is never turned into a
// float here. Anything that is not a plain decimal is shown as supplied.
const DECIMAL = /^-?\d+(\.\d+)?$/;
function money(value) {
  const text = String(value).replace(/,/g, "");
  return DECIMAL.test(text) ? GBP.format(text) : String(value);
}
function amount(value) {
  const text = String(value).replace(/,/g, "");
  return DECIMAL.test(text) ? PLAIN.format(text) : String(value);
}
// Gate details and claims carry engine text: Decimal reprs, 40-digit fractions and exponents are shortened for reading.
function tidy(text) {
  return String(text).replace(/Decimal\('([^']+)'\)/g, "$1").replace(/-?\d+(\.\d+)?E-\d{2,}/g, "0")
    .replace(/(\d+\.\d{6})\d+/g, "$1");
}
function figureValue(x) {
  if (x.value === null) return h("span", { class: "unknown" }, "Not determinable");
  if (typeof x.value === "object") return Object.entries(x.value).map(([k, v]) => `${v} ${k}`).join(" · ");
  return money(x.value);
}
// A provisional badge says why; the same text is in the callout below the table so touch screens can read it too.
function statusBadge(x) {
  const why = x.status === "provisional" ? (x.open_items || []).join("; ") : x.status === "unknown" ? x.reason || "" : "";
  const label = { determined: "Determined", provisional: "Provisional", unknown: "Not determinable" }[x.status] || x.status;
  return h("span", { class: `tag ${x.status}`, title: why || null, tabindex: why ? "0" : null }, label);
}
function figuresTable(figures) {
  const rows = figures.map((x) => h("tr", {}, h("td", {}, FIGURE_NAMES[x.key] || x.key, h("div", { class: "muted small figkey" }, h("code", {}, x.key))),
    h("td", { class: "num" }, figureValue(x)), h("td", {}, statusBadge(x))));
  const nulls = figures.filter((x) => x.value === null).map((x) =>
    h("div", { class: "callout bad" }, h("strong", {}, `${FIGURE_NAMES[x.key] || x.key}: `), "Not determinable. " + tidy(x.reason || "No reason was recorded.")));
  const reasons = new Map();  // one callout per distinct reason, naming every figure that rests on it
  for (const x of figures.filter((f) => f.value !== null && f.status === "provisional")) {
    const why = tidy((x.open_items || []).join("; "));
    reasons.set(why, [...(reasons.get(why) || []), FIGURE_NAMES[x.key] || x.key]);
  }
  const notes = [...nulls, ...[...reasons].map(([why, names]) =>
    h("div", { class: "callout warn" }, h("strong", {}, `Provisional: ${names.join(", ")}. `), why))];
  return h("div", {}, h("div", { class: "scroll" }, h("table", {}, h("thead", {}, h("tr", {}, h("th", {}, "Figure"),
    h("th", { class: "num" }, "Value (GBP)"), h("th", {}, "Status"))), h("tbody", {}, rows))), notes);
}
