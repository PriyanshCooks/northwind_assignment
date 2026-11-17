// The recorded AI review and the build log. Both are replays of what was really recorded: no live call, no timer.
function stat(label, value) { return h("div", { class: "stat" }, h("div", { class: "muted small" }, label), h("div", { class: "big" }, value)); }

function unitVerdict(u) {
  if (!u.recorded) return "No recorded answer: rules used";
  const bits = [];
  if (u.verified.length) bits.push(`${u.verified.length} verified`);
  if (u.dropped.length) bits.push(`${u.dropped.length} dropped`);
  if (u.missed.length) bits.push(`missed ${u.missed.length}`);
  return bits.join(", ") || "no claims";
}

function unitRow(u) {
  const answer = u.answer ? Object.entries(u.answer).map(([k, v]) => `${k}: ${v}`).join("\n") : "No recorded model answer for this unit.";
  const grounding = [...u.verified.map((c) => `verified: ${c}`), ...u.unverified.map((c) => `not checkable: ${c}`),
    ...u.dropped.map((d) => `dropped: ${d.claim} (${d.why})`), ...u.missed.map((c) => `the rules found ${c} and the answer did not report it`)];
  return h("details", { class: "unit" }, h("summary", {}, h("code", {}, u.unit), ` ${u.kind} · ${unitVerdict(u)}`),
    h("h4", {}, "Evidence packet sent to the model"), h("pre", {}, JSON.stringify(u.packet, null, 2)),
    h("h4", {}, "The model's recorded answer"), h("pre", {}, answer),
    h("h4", {}, "Grounding verdict"), grounding.length ? h("ul", {}, grounding.map((g) => h("li", {}, g))) : h("p", { class: "muted" }, "No claims to check."));
}

function aiPanel(ai) {
  const t = ai.totals;
  const cost = t.cost_usd === null ? "not priced" : `$${t.cost_usd} (${t.cost_note})`;
  return h("section", {}, h("h2", {}, "AI review ", h("span", { class: "tag" }, "recorded review")),
    h("p", { class: "muted" }, `Replayed from ${ai.ledger}. Nothing is called now; the answers were recorded earlier and the review is advice that changes no figure.`),
    h("div", { class: "stats" }, stat("Model", ai.model), stat("Units reviewed", t.units), stat("With a recorded answer", t.units_with_recorded_answer),
      stat("Claims made", t.claims), stat("Verified", t.verified), stat("Dropped", t.dropped),
      stat("Tokens in / out", `${t.input_tokens.toLocaleString("en-GB")} / ${t.output_tokens.toLocaleString("en-GB")}`), stat("Cost of the recording", cost)),
    ai.units.map(unitRow));
}

// Stages come from the run's own log file; the times are when each was recorded, not a live clock.
function stageList(stages) {
  if (!stages.length) return h("p", { class: "muted" }, "This run wrote no log events.");
  const detail = (e) => ["count", "blocked", "checks_passed"].filter((k) => k in e).map((k) => `${k.replace("_", " ")}: ${e[k] ?? "none"}`).join(", ");
  return h("ol", { class: "stages" }, stages.map((e) => h("li", {}, h("strong", {}, e.stage), ` – ${e.event}`,
    detail(e) ? ` (${detail(e)})` : "", h("span", { class: "muted small" }, ` · logged ${new Date(e.ts).toLocaleString("en-GB")}`))));
}
