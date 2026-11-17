// Issue cards. The wording comes from the server (cards_service); this file only lays it out.
const SEVERITY = { BLOCK: ["Blocking", "bad"], FLAG: ["Flagged", "warn"], NOTE: ["Noted", "muted"] };
const AI_STATE = { agrees: "AI agrees", disagrees: "AI disagrees", no_claim: "Reviewed by the AI, not flagged", not_reviewed: "Not reviewed" };

function field(label, ...body) { return h("div", { class: "field" }, h("dt", {}, label), h("dd", {}, ...body)); }

function issueCard(card, marks, refresh) {
  const [sevText, sevClass] = SEVERITY[card.severity];
  const where = card.evidence.line == null ? card.evidence.file : `${card.evidence.file}, line ${card.evidence.line}`;
  const choose = (action) => () => { marks[card.key] = marks[card.key] === action ? undefined : action; refresh(); };
  const buttons = card.actions.map((a) => h("button", { class: marks[card.key] === a ? "" : "plain", "aria-pressed": String(marks[card.key] === a),
    onclick: choose(a) }, a === "approve" ? "Approve" : "Reject"));
  return h("article", { class: `card sev-${sevClass}` },
    h("div", { class: "card-head" }, h("span", { class: `tag ${sevClass}` }, sevText), h("code", { title: "detector code" }, card.code)),
    h("h3", {}, card.headline),
    h("dl", {}, field("Evidence", where), card.quote ? field("The text, quoted as data", h("q", {}, card.quote)) : null,
      field("What the rules decided", card.rules),
      field("What the AI reviewer said", h("span", { class: `tag ai-${card.ai.state}` }, AI_STATE[card.ai.state]), " ", card.ai.text),
      card.dropped.length ? field("Claims dropped by grounding", h("ul", {}, card.dropped.map((d) => h("li", {}, h("code", {}, d.claim), ": ", d.why)))) : null),
    buttons.length ? h("div", { class: "row" }, ...buttons, h("span", { class: "muted small" }, "Needs your decision")) : null);
}

// Cards grouped by what needs a decision, then by severity.
function issueGroups(cards, marks, refresh) {
  const groups = [["Needs your decision", cards.filter((c) => c.needs_decision)]];
  for (const sev of ["BLOCK", "FLAG", "NOTE"]) {
    groups.push([`${SEVERITY[sev][0]}, decided by the rules`, cards.filter((c) => !c.needs_decision && c.severity === sev)]);
  }
  if (!cards.length) return [h("div", { class: "callout ok" }, "No issues were found.")];
  return groups.filter(([, list]) => list.length).map(([title, list]) =>
    h("section", {}, h("h2", {}, `${title} (${list.length})`), list.map((c) => issueCard(c, marks, refresh))));
}

// A waiting item (an override that is open or stale): what it is, why, and what each choice does.
function waitingCard(item, marks, refresh) {
  const choose = (action) => () => { marks[item.key] = marks[item.key] === action ? undefined : action; refresh(); };
  const pick = (action, label) => h("button", { class: marks[item.key] === action ? "" : "plain", "aria-pressed": String(marks[item.key] === action),
    onclick: choose(action) }, label);
  return h("article", { class: "card sev-warn" },
    h("div", { class: "card-head" }, h("span", { class: "tag warn" }, item.state === "stale" ? "Stale" : "Open"), h("code", {}, item.key)),
    h("h3", {}, item.headline),
    h("dl", {}, field("Why it is waiting", item.reason), field("If you approve", item.approve_effect), field("If you reject", item.reject_effect)),
    h("div", { class: "row" }, pick("approve", "Approve"), pick("reject", "Reject")));
}
