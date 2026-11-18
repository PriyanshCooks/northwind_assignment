// Review outputs: the generated files on the left with a reviewed mark, the selected file as a row list, and a drawer for the
// clicked row with the calculation behind it. Every value is shown as the file has it; the page calculates nothing.
const MONEY_COLUMN = /debit|credit|amount|gbp|balance|total/i;
const KEY_COLUMN = /^(group_code|account|field)$/i;  // the cell that names a control figure or a group account
const isNumber = (t) => /^-?\d+(\.\d+)?$/.test(t);
const SIGN_WORD = { reviewed: "Reviewed", open: "Open", stale: "Changed since reviewed" };

function targetOf(section, row) {
  const i = section.columns.findIndex((c) => KEY_COLUMN.test(c));
  return i < 0 ? null : row[i];
}

function sectionTable(s, si, picked, onpick, done) {
  const numeric = s.columns.map((c, i) => MONEY_COLUMN.test(c) && s.rows.some((r) => isNumber(r[i])));
  const cell = (v, i) => (numeric[i] && isNumber(v) ? h("td", { class: "num" }, money(v)) : h("td", { class: "lines" }, v));
  const row = (r, ri) => h("tr", { class: `wb-row ${picked === `${si}:${ri}` ? "selected" : ""}`, tabindex: "0",
    onclick: () => onpick(si, ri), onkeydown: (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onpick(si, ri); } } },
    r.map(cell), h("td", { class: done.has(`${si}:${ri}`) ? "ok small" : "muted small" }, done.has(`${si}:${ri}`) ? "\u2713 reviewed" : "open"));
  return h("div", {}, s.title ? h("h3", {}, s.title) : null, h("div", { class: "scroll" }, h("table", { class: "wb-table" },
    h("thead", {}, h("tr", {}, s.columns.map((c, i) => h("th", { class: numeric[i] ? "num" : "" }, c)), h("th", {}, "Review"))),
    h("tbody", {}, s.rows.map(row)))));
}

function calcBlock(calc) {
  if (!calc) return h("p", { class: "muted" }, "No calculation is recorded for this row: it is a label or a total the engine did not build from postings.");
  return h("div", {}, h("h3", {}, calc.kind === "figure" ? "How the figure is built" : "Postings that make this account"),
    h("ol", { class: "calc" }, calc.steps.map((s) => h("li", {}, h("span", { class: "lines" }, s.formula),
      s.result ? h("strong", {}, ` = ${money(s.result)}`) : null,
      s.sources.length ? h("div", { class: "muted small" }, "from ", s.sources.join(", ")) : null))));
}

function outputDrawer(state, close, markRow, done) {
  if (!state.pick) return h("aside", { class: "wb-drawer", hidden: true });
  const { section, row } = state.pick;
  const target = targetOf(section, row);
  return h("aside", { class: "wb-drawer", "aria-label": "Calculation behind this row" },
    h("div", { class: "row" }, h("h2", {}, target ? `${state.name}: ${target}` : state.name), h("button", { class: "plain", onclick: close }, "Close")),
    h("div", { class: "callout" }, "Checked by the 20 gates and the oracle, a second implementation of the same method. " +
      "No AI agent reviews the generated figures."),
    h("dl", { class: "cells" }, section.columns.map((c, i) => h("div", {}, h("dt", {}, c), h("dd", { class: "lines" }, row[i] || "(empty)")))),
    target ? calcBlock(state.calc) : null,
    h("div", { class: "wb-ai" }, done ? h("p", { class: "ok" }, "You marked this row reviewed.") :
      h("div", { class: "row" }, h("input", { placeholder: "your name", maxlength: 60, "aria-label": "Your name", value: reviewerName,
        oninput: (e) => { reviewerName = e.target.value; } }), button("Mark this row reviewed", markRow))));
}

function fileBadge(f, current, onpick) {
  return h("button", { class: `wb-file ${f.name === current ? "current" : ""}`, "aria-current": f.name === current ? "true" : null,
    onclick: () => onpick(f.name) }, h("span", { class: "wb-name" }, f.name),
    h("span", { class: `badge ${f.state === "reviewed" ? "reviewed" : "open"}` }, f.state === "reviewed" ? "✓" : "!"),
    h("span", { class: "muted small" }, SIGN_WORD[f.state] + (f.reviewed_by ? ` by ${f.reviewed_by}` : "")));
}

function affectingBlock(got) {
  const none = (text) => h("p", { class: "muted" }, text);
  return h("details", {}, h("summary", {}, `Issues traced to this file (${got.affecting.length}) and run-wide (${got.run_wide.length})`),
    got.affecting.length ? issueGroups(got.affecting, {}, () => {}) : none("No issue traces to this file through its source rows."),
    got.run_wide.length ? issueGroups(got.run_wide, {}, () => {}) : null);
}

async function filesStep(run) {
  const state = { name: null, view: null, sign: null, side: null, pick: null, calc: null };
  const holder = h("div", { class: "wb" });
  const bar = h("div", { class: "row topbar" });
  const load = async () => {
    state.side = null;
    state.view = await api("GET", `/runs/${run.id}/output-files/${encodeURIComponent(state.name)}`).catch((e) => ({ error: e.message }));
    draw();  // the rows first; the issue lookup is slower and fills in below them
    if (state.name === "issues.json") return;
    const asked = state.name;
    const side = await api("GET", `/runs/${run.id}/output-files/${encodeURIComponent(asked)}/issues`).catch(() => null);
    if (side && state.name === asked) { state.side = side; draw(); }
  };
  const pickFile = async (name) => { state.name = name; state.pick = null; history.replaceState(null, "", `#/run/${run.id}/files/${encodeURIComponent(name)}`); await load(); };
  const pickRow = async (si, ri) => {
    const section = state.view.sections[si], row = section.rows[ri];
    state.pick = { key: `${si}:${ri}`, section, row };
    const target = targetOf(section, row);
    state.calc = target ? await api("GET", `/runs/${run.id}/calculation/${encodeURIComponent(target)}`).catch(() => null) : null;
    draw();
  };
  const markRow = async () => {
    try { state.sign = await api("POST", `/runs/${run.id}/signoff`, { file: state.name, reviewer: reviewerName, row: state.pick.key }); draw(); } catch (e) { fail(e); }
  };
  const mark = async () => {
    try { state.sign = await api("POST", `/runs/${run.id}/signoff`, { file: state.name, reviewer: reviewerName }); draw(); } catch (e) { fail(e); }
  };
  const draw = () => {
    const me = state.sign.files.find((f) => f.name === state.name);
    const name = h("input", { placeholder: "your name", maxlength: 60, "aria-label": "Your name", value: reviewerName, oninput: (e) => { reviewerName = e.target.value; } });
    const v = state.view;
    holder.classList.toggle("has-drawer", state.pick != null);
    holder.replaceChildren(
      h("nav", { class: "wb-files", "aria-label": "Output files" }, h("p", { class: "muted small" }, "files that will be exported"),
        state.sign.files.map((f) => fileBadge(f, state.name, pickFile))),
      h("section", { class: "wb-rows" }, h("h2", {}, state.name),
        h("div", { class: "row" }, h("span", { class: me.state === "reviewed" ? "ok" : "bad" }, SIGN_WORD[me.state] + (me.reviewed_by ? ` by ${me.reviewed_by}` : "")),
          me.state === "reviewed" ? null : [name, button("Mark reviewed", mark)]),
        v.error ? h("div", { class: "callout warn" }, v.error) : [h("p", { class: "muted" }, `${v.total_rows} rows · sha256 `, h("code", {}, v.sha256), ". Click a row to see the calculation behind it."),
          ...v.sections.map((s, si) => sectionTable(s, si, state.pick && state.pick.key, pickRow, new Set(me.rows_reviewed))),
          v.truncated ? h("div", { class: "callout warn" }, `Showing the first rows of ${v.total_rows}. Download the file for all of them.`) : null,
          h("p", {}, h("a", { class: "btn plain", href: `/api/runs/${run.id}/output-files/${encodeURIComponent(state.name)}/download`, download: state.name }, "Download this file"))],
        state.side ? affectingBlock(state.side) : null),
      outputDrawer(state, () => { state.pick = null; draw(); }, markRow, state.pick && me.rows_reviewed.includes(state.pick.key)));
    const s = state.sign;
    bar.replaceChildren(h("span", { class: `tag ${s.status === "Final" ? "determined" : "provisional"}` }, s.status),
      h("span", { class: "muted", role: "status" }, s.reasons.length ? s.reasons.join(". ") + "." : "Every problem is answered and every file is reviewed."),
      button("Next stage: done", () => go(run, "export")));
  };
  state.sign = await api("GET", `/runs/${run.id}/signoff`);
  const first = state.sign.files;
  const wanted = decodeURIComponent(location.hash.split("/")[4] || "");
  state.name = (first.find((f) => f.name === wanted) || first[0]).name;
  show(...head(run, "6 Review outputs"), bar, holder);
  document.onkeydown = (e) => { if (e.key === "Escape" && state.pick && location.hash.includes("/files")) { state.pick = null; draw(); } };
  await load();
}
