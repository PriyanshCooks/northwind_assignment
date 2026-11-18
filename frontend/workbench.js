// Review inputs: the workbench. Files on the left with an open/total badge, the selected file's rows in the middle
// (red = blocking, amber = flagged, grey = noted) and the why-drawer for the selected row on the right.
// Everything shown comes from the server; the page only records Pass or Override with the reviewer's name.
const SEV_WORD = { BLOCK: "Blocking", FLAG: "Flagged", NOTE: "Noted" };
const REVIEW_WORD = { clean: "No issue", open: "Open", stale: "Stale", reviewed: "Reviewed", noted: "Noted" };
const STATE_WORD = { open: "Open", stale: "Stale: the row changed since it was decided", noted: "Noted, no decision needed",
                     passed: "Passed", overridden: "Overridden" };
let reviewerName = "";  // typed once, kept while the page is open

function who(findings) {
  const names = [...new Set(findings.filter((f) => f.decision && ["passed", "overridden"].includes(f.state)).map((f) => f.decision.reviewer))];
  return names.length ? ` by ${names.join(", ")}` : "";
}

function fileButton(f, current, onpick) {
  const badge = f.present ? `${f.open}/${f.total}` : "missing";
  return h("button", { class: `wb-file ${f.name === current ? "current" : ""}`, disabled: !f.present, "aria-current": f.name === current ? "true" : null,
    onclick: () => onpick(f.name) },
    h("span", { class: "wb-name" }, f.name),
    h("span", { class: `badge ${f.status}`, title: "problems open / problems found" }, badge),
    h("span", { class: "muted small" }, f.present ? { clean: "No issues", open: "Open", reviewed: "Reviewed", noted: "Notes only" }[f.status] : "Not uploaded"));
}

function rowTable(view, line, onpick) {
  const labels = [...new Set(view.rows.flatMap((r) => r.cells.map((c) => c.label)))];
  const head = ["Line", ...labels, "Review"];
  const body = view.rows.map((r) => {
    const byLabel = Object.fromEntries(r.cells.map((c) => [c.label, c.value]));
    const flagged = r.severity ? `sev-${r.severity}` : "";
    const open = () => onpick(r.line);
    return h("tr", { class: `wb-row ${flagged} ${r.line === line ? "selected" : ""}`, tabindex: "0", "aria-selected": String(r.line === line),
      onclick: open, onkeydown: (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); open(); } } },
      h("td", { class: "num" }, r.line), labels.map((l) => h("td", { class: "lines" }, byLabel[l] ?? "")),
      h("td", {}, r.severity ? h("span", { class: `tag sev-tag-${r.severity}` }, SEV_WORD[r.severity]) : null, " ",
        h("span", { class: `review ${r.review}` }, REVIEW_WORD[r.review] + (r.review === "reviewed" ? who(r.findings) : ""))));
  });
  return h("div", { class: "scroll" }, h("table", { class: "wb-table" },
    h("thead", {}, h("tr", {}, head.map((t) => h("th", {}, t)))), h("tbody", {}, body)));
}

function decisionBox(f, send) {
  if (["passed", "overridden"].includes(f.state)) {
    const d = f.decision;
    return h("p", { class: "ok" }, `${STATE_WORD[f.state]} by ${d.reviewer} on ${when(d.at)}.` + (d.note ? ` Note: ${d.note}` : ""));
  }
  const note = h("input", { placeholder: "note (optional)", maxlength: 500, "aria-label": "Note" });
  const name = h("input", { placeholder: "your name", maxlength: 60, "aria-label": "Your name", value: reviewerName,
    oninput: (e) => { reviewerName = e.target.value; } });
  const problem = h("div", { class: "error", role: "alert", hidden: true });
  const go = (action) => async () => {
    if (!reviewerName.trim()) { problem.textContent = "Enter your name before you decide."; problem.hidden = false; return; }
    try { await send(f.key, action, reviewerName, note.value); } catch (e) { problem.textContent = e.message; problem.hidden = false; }
  };
  return h("div", {}, f.state === "stale" ? h("p", { class: "warn" }, STATE_WORD.stale + ". Decide again.") : null,
    h("div", { class: "row" }, name, note),
    h("div", { class: "row" }, h("button", { onclick: go("pass"), title: "Acknowledge it: no figure changes" }, "Pass"),
      f.actions.override ? h("button", { class: "plain", onclick: go("override"), title: "Apply the engine's override" }, "Override") : null,
      h("span", { class: "muted small" }, "Leave it open by doing nothing.")),
    f.actions.override ? null : h("p", { class: "muted small" }, f.actions.override_note), problem);
}

function findingBlock(f, send) {
  return h("section", { class: `wb-finding sev-${f.severity}` },
    h("div", { class: "card-head" }, h("span", { class: `tag sev-tag-${f.severity}` }, SEV_WORD[f.severity]), h("code", {}, f.code),
      h("span", { class: "tag" }, f.source)),
    h("h3", {}, f.headline),
    h("dl", {},
      field("Why it is flagged", f.rule.what), field("Policy or brief reference", f.rule.policy),
      field("Evidence", f.evidence.cited.join(", "), h("dl", { class: "cells" },
        f.evidence.values.map((c) => h("div", {}, h("dt", {}, c.label), h("dd", { class: "lines" }, c.value || "(empty)"))))),
      field("What the rules decided", f.rules_decided),
      field("Status", STATE_WORD[f.state])),
    decisionBox(f, send));
}

function aiBlock(ai) {
  const dropped = ai.dropped.length ? h("ul", {}, ai.dropped.map((d) => h("li", {}, h("code", {}, d.claim), ": ", d.why))) : null;
  return h("section", { class: "wb-ai" }, h("h3", {}, "What the AI said about this row"),
    h("p", {}, h("span", { class: `tag ai-${ai.state}` }, AI_STATE[ai.state]), " ", ai.text),
    ai.model_reason ? h("p", {}, "The model's own words: ", h("q", {}, ai.model_reason)) : null,
    ai.dropped.length ? h("div", {}, h("strong", {}, "Claims dropped because the data does not back them"), dropped) : null,
    ai.missed.length ? h("p", {}, `The recorded answer did not report: ${ai.missed.join(", ")}.`) : null);
}

function drawer(explain, send, close) {
  if (!explain) return h("aside", { class: "wb-drawer muted" }, h("p", {}, "Select a row to see why it is flagged, what the rule is and what the AI said."));
  return h("aside", { class: "wb-drawer", "aria-label": "Why this row" },
    h("div", { class: "row" }, h("h2", {}, `${explain.file}, line ${explain.line}`), h("button", { class: "plain", onclick: close }, "Close")),
    explain.findings.length ? explain.findings.map((f) => findingBlock(f, send)) :
      h("p", { class: "callout ok" }, "No rule flagged this row."),
    aiBlock(explain.ai));
}

// The recorded AI review in full (every unit, tokens and cost), read only when the reviewer opens it.
function recordedReview(run) {
  const body = h("div");
  const box = h("details", {}, h("summary", {}, "The recorded AI review: every unit, tokens and cost"), body);
  box.addEventListener("toggle", async () => {
    if (!box.open || body.childNodes.length) return;
    try { body.replaceChildren(aiPanel((await api("GET", `/runs/${run.id}/review`)).ai)); } catch (e) { body.replaceChildren(String(e.message)); }
  });
  return box;
}

async function reviewStep(run) {
  const state = { run, files: [], name: null, view: null, line: null, explain: null };
  const holder = h("div", { class: "wb" });
  const bar = h("div", { class: "row topbar" });
  const load = async (scroll = false) => {
    [state.run, state.files, state.left] = await Promise.all([api("GET", `/runs/${run.id}`), api("GET", `/runs/${run.id}/inputs`),
      api("GET", `/runs/${run.id}/unanswered`)]);
    state.view = await api("GET", `/runs/${run.id}/inputs/${state.name}/rows`);
    state.explain = state.line == null ? null : await api("GET", `/runs/${run.id}/inputs/${state.name}/rows/${state.line}/explain`);
    draw();
    if (scroll && state.explain) holder.querySelector(".wb-drawer")?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  };
  const pickFile = async (name) => {
    state.name = name; state.line = null;
    history.replaceState(null, "", `#/run/${run.id}/review/${encodeURIComponent(name)}`);
    await load();
  };
  const pickRow = async (line) => { state.line = line; await load(true); };
  const send = async (key, action, reviewer, note) => {
    await api("POST", `/runs/${run.id}/inputs/${state.name}/decisions`, { key, action, reviewer, note });
    await load();
  };
  const draw = () => {
    const v = state.view;
    holder.replaceChildren(
      h("nav", { class: "wb-files", "aria-label": "Input files" }, h("p", { class: "muted small" }, "open / total problems per file"),
        state.files.map((f) => fileButton(f, state.name, pickFile))),
      h("section", { class: "wb-rows" },
        h("h2", {}, state.name), h("p", { class: "muted" }, `${v.total_rows} rows. Review status: ${v.review.status}. `,
          `Each finding is labelled Rule or Rule + AI view; the AI reads journals and trial-balance mappings only.`),
        v.file_findings.length ? h("div", { class: "callout warn" }, "Findings not tied to one row: ", v.file_findings.map((f) => `${f.code} ${f.headline}`).join("; ")) : null,
        rowTable(v, state.line, pickRow)),
      drawer(state.explain, send, () => pickRow(null)));
    const open = state.left.problems;
    bar.replaceChildren(h("button", { onclick: () => go(run, "build") }, "Generate output"),
      h("span", { class: open ? "bad" : "ok", role: "status" }, open ?
        `${open} problem(s) still open. You can generate now: the output will be a Draft and they stay marked as problems.` :
        "Nothing is open. The output will not be a Draft."));
  };
  const files = await api("GET", `/runs/${run.id}/inputs`);
  const wanted = decodeURIComponent(location.hash.split("/")[4] || "");
  const first = files.find((f) => f.name === wanted && f.present) || files.find((f) => f.present && f.open) || files.find((f) => f.present);
  if (!first) return show(...head(run, "3 Review inputs"), h("div", { class: "callout" }, "This run has no input files yet."));
  state.name = first.name;
  show(...head(run, "3 Review inputs"),
    h("div", { class: "callout" }, "Pass acknowledges a finding and changes no figure. Override appears only where the engine has a mechanism. " +
      "Anything left open stays marked as a problem."), bar, holder, recordedReview(run));
  await load();
}
