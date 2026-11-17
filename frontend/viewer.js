// Output viewer: one generated file at a time, as tables or cards, with what affects it. Every value is shown as the file has it.
const MONEY_COLUMN = /debit|credit|amount|gbp|balance|total/i;
const isNumber = (t) => /^-?\d+(\.\d+)?$/.test(t);

function sectionTable(s) {
  const numeric = s.columns.map((c, i) => MONEY_COLUMN.test(c) && s.rows.some((r) => isNumber(r[i])));
  const cell = (v, i) => (numeric[i] && isNumber(v) ? h("td", { class: "num" }, amount(v)) : h("td", {}, v));
  return h("div", {}, s.title ? h("h3", {}, s.title) : null, h("div", { class: "scroll" }, h("table", {},
    h("thead", {}, h("tr", {}, s.columns.map((c, i) => h("th", { class: numeric[i] ? "num" : "" }, c)))),
    h("tbody", {}, s.rows.map((r) => h("tr", {}, r.map(cell)))))));
}

async function fileBody(run, file) {
  if (file.name === "control_figures_pb.json") return figuresTable((await api("GET", `/runs/${run.id}/results`)).figures);
  if (file.name === "issues.json") return h("div", {}, issueGroups((await api("GET", `/runs/${run.id}/results`)).cards, {}, () => {}));
  const view = await api("GET", `/runs/${run.id}/output-files/${file.name}`);
  return h("div", {}, view.sections.map(sectionTable), view.truncated ?
    h("div", { class: "callout warn" }, `Showing the first ${view.sections.reduce((n, s) => n + s.rows.length, 0)} of ${view.total_rows} rows. Download the file for all of them.`) : null);
}

async function affecting(run, file) {
  if (file.name === "issues.json") return h("p", { class: "muted" }, "This file lists every issue of the run.");
  const got = await api("GET", `/runs/${run.id}/output-files/${file.name}/issues`);
  const none = (text) => h("p", { class: "muted" }, text);
  return h("div", {}, h("h3", {}, `Traced to this file (${got.affecting.length})`),
    got.affecting.length ? issueGroups(got.affecting, {}, () => {}) : none("No issue traces to this file through its source rows."),
    h("h3", {}, `Run-wide (${got.run_wide.length})`),
    h("p", { class: "muted small" }, "These could not be traced to this file, so they are listed for the whole run and not guessed onto it."),
    got.run_wide.length ? issueGroups(got.run_wide, {}, () => {}) : none("None."));
}

async function filesStep(run) {
  const list = await api("GET", `/runs/${run.id}/output-files`);
  if (!list.length) return show(...head(run, "6 Output files"), h("div", { class: "callout" }, "This run has no output files yet."));
  const wanted = decodeURIComponent(location.hash.split("/")[4] || "");
  const at = Math.max(0, list.findIndex((f) => f.name === wanted));
  const file = list[at];
  const open = (i) => () => { location.hash = `#/run/${run.id}/files/${encodeURIComponent(list[i].name)}`; };
  show(...head(run, "6 Output files"),
    h("div", { class: "row" }, button("Previous", open(at - 1), true), h("strong", {}, `File ${at + 1} of ${list.length}`),
      button("Next", open(at + 1), true)),
    h("div", { class: "row" }, h("select", { "aria-label": "Choose a file", onchange: (e) => open(Number(e.target.value))() },
      list.map((f, i) => h("option", { value: i, selected: i === at }, f.name)))),
    h("h2", {}, file.name),
    h("p", { class: "muted" }, `${file.rows === null ? "rows not counted" : `${file.rows} rows`} · ${file.bytes.toLocaleString("en-GB")} bytes · sha256 `, h("code", {}, file.sha256)),
    h("div", { class: "row" }, h("a", { class: "btn", href: `/api/runs/${run.id}/output-files/${file.name}/download`, download: file.name }, "Download")),
    await fileBody(run, file), h("h2", {}, "Issues and AI notes affecting this file"), await affecting(run, file));
  const buttons = view.querySelectorAll("button.plain");
  if (at === 0) buttons[0].disabled = true;
  if (at === list.length - 1) buttons[1].disabled = true;
}
