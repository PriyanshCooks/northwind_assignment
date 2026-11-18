// The six step views. Each reads from the API and draws; no number is calculated here.
const head = (run, title) => [h("h1", {}, title), h("p", { class: "muted" }, run.name + " · ", h("code", {}, run.id))];
const go = (run, step) => { location.hash = `#/run/${run.id}/${step}`; };
const button = (label, onclick, plain) => h("button", { onclick, class: plain ? "plain" : "" }, label);

// Upload: one file at a time. Each of the 15 expected files has its own chooser and its own mark: uploaded, rejected
// with the contract's reason, or not uploaded. A file is stored only if it passes its contract.
async function uploadStep(run, notes = {}) {
  const fresh = await api("GET", `/runs/${run.id}`);
  const ready = fresh.files.every((f) => f.present && !f.error);
  const pick = (f) => h("input", { type: "file", "aria-label": `Choose ${f.name}`, onchange: async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    try {
      const r = await api("PUT", `/runs/${run.id}/files/${encodeURIComponent(f.name)}`, undefined, await file.arrayBuffer());
      notes[f.name] = r.stored ? null : r.error;
    } catch (err) { notes[f.name] = err.message; }
    await uploadStep(run, notes);
  } });
  const mark = (f) => notes[f.name] ? h("span", { class: "bad" }, "Rejected") :
    f.present && !f.error ? h("span", { class: "ok" }, "Uploaded") : h("span", { class: "muted" }, "Not uploaded");
  const rows = fresh.files.map((f) => [h("code", {}, f.name), mark(f), f.present ? `${f.bytes} bytes` : "",
    notes[f.name] || f.error || "", pick(f)]);
  const uploaded = fresh.files.filter((f) => f.present && !f.error).length;
  const next = () => go(run, "scan");
  show(...head(run, "1 Upload"), h("div", { class: "callout" }, "Add the files one at a time: choose a file on its own row. Only the 15 " +
    "expected names are accepted, up to 1 MB each, and a file that breaks its contract is refused with the reason shown."),
    h("p", { role: "status" }, `${uploaded} of ${fresh.files.length} files uploaded.`),
    table(["File", "Mark", "Size", "Contract", "Choose a file"], rows),
    h("div", { class: "row" }, h("button", { onclick: next, disabled: !ready }, "Next: scan the files")));
}

// Scan: the analysis runs on the server and the page reads the run log while it works. Each file's status is a log event.
async function scanStep(run) {
  const holder = h("div");
  const draw = (p) => holder.replaceChildren(
    h("progress", { max: p.total, value: p.scanned, "aria-label": "Files scanned" }),
    h("p", { role: "status" }, `${p.scanned} of ${p.total} files scanned` + (p.finished ? ". The scan is finished." : "…")),
    table(["File", "Status", "Findings"], p.files.map((f) => [h("code", {}, f.name),
      h("span", { class: f.status === "scanned" ? "ok" : f.status === "missing" ? "bad" : "muted" },
        { scanned: "Scanned", waiting: "Waiting", missing: "Not uploaded" }[f.status]), f.findings == null ? "" : f.findings])));
  const next = h("button", { onclick: () => go(run, "review"), disabled: true }, "Next: review the inputs");
  show(...head(run, "2 Scan"), h("div", { class: "callout" }, "The rules (D01 to D15) read every file. The AI reviewers read journals and " +
    "trial-balance mappings only, and their answers are replayed from the recorded ledger: no model is called."), holder,
    h("div", { class: "row" }, next));
  draw(await api("GET", `/runs/${run.id}/scan`));
  let failure = null;
  const working = run.status === "new" ? api("POST", `/runs/${run.id}/analyse`).catch((e) => { failure = e; }) : Promise.resolve();
  let p = await api("GET", `/runs/${run.id}/scan`);
  while (!p.finished && !failure && location.hash.includes("/scan")) {
    draw(p);
    await new Promise((r) => setTimeout(r, 300));
    p = await api("GET", `/runs/${run.id}/scan`);
  }
  await working;
  if (failure) return fail(failure);
  draw(p);
  next.disabled = false;
}

// Choose outputs comes before generating: the choice is stored and decides which files the review and the zip hold.
async function outputsStep(run) {
  const plan = await api("GET", `/runs/${run.id}/output-plan`);
  const picked = new Set(plan.chosen || plan.available.map((o) => o.name));
  const boxes = plan.available.map((o) => h("input", { type: "checkbox", checked: picked.has(o.name) || o.required, disabled: o.required,
    "aria-label": `Export ${o.name}`, onchange: (e) => (e.target.checked ? picked.add(o.name) : picked.delete(o.name)) }));
  const save = async () => { try { await api("PUT", `/runs/${run.id}/output-plan`, { files: [...picked] }); go(run, "build"); } catch (e) { fail(e); } };
  show(...head(run, "4 Choose outputs"), h("div", { class: "callout" }, "Tick the files to export. Every file is built; the choice decides what you review " +
    "and what goes in the zip. The run manifest is always included. Open items keep the result a Draft."),
    table(["", "File"], plan.available.map((o, i) => [boxes[i], h("code", {}, o.name)])),
    h("div", { class: "row" }, button("Next stage: generate", save)));
}

// Generate: the page lists the files at once as building, then marks each generated when the server has written it.
async function buildStep(run) {
  const plan = await api("GET", `/runs/${run.id}/output-plan`);
  const names = plan.chosen || plan.available.map((o) => o.name);
  const fileRows = (made, missing = "Building…") => table(["File", "Status", "Size"], names.map((n) => [h("code", {}, n),
    h("span", { class: made[n] ? "ok" : missing === "Building…" ? "muted" : "bad" }, made[n] ? "Generated" : missing), made[n] ? `${made[n].toLocaleString("en-GB")} bytes` : ""]));
  const progress = (made) => h("progress", { max: names.length, value: names.filter((n) => made[n]).length, "aria-label": "Files generated" });
  show(...head(run, "5 Generate"), progress({}), h("p", { role: "status" }, "Generating the output files…"), fileRows({}));
  const b = await api("POST", `/runs/${run.id}/generate`);
  const made = Object.fromEntries((await api("GET", `/runs/${run.id}/output-files`)).map((f) => [f.name, f.bytes]));
  const left = b.unanswered;
  const draft = b.draft ? h("div", { class: "callout warn" }, h("strong", {}, "Draft. "),
    `${left.problems} problem(s) are still unanswered, so this output is not final. They stay marked as problems:`,
    h("ul", {}, left.engine_items.map((t) => h("li", {}, h("code", {}, t), " waits for a decision")),
      left.findings.map((f) => h("li", {}, h("a", { href: `#/run/${run.id}/review/${encodeURIComponent(f.file)}` }, `${f.file}:${f.line ?? ""}`),
        ` ${f.code} ${f.headline}`)))) : h("div", { class: "callout ok" }, "Nothing is unanswered. This output is not a Draft.");
  show(...head(run, "5 Generate"), progress(made), h("p", { role: "status" }, `${names.filter((n) => made[n]).length} of ${names.length} files generated.`),
    fileRows(made, "Not produced"), draft, b.blocked ? h("div", { class: "error", role: "alert" },
      h("strong", {}, "The run is blocked, so the statements were not produced. "), `Reason: ${b.blocked}. Correct the input and scan again.`)
      : h("div", { class: b.passed ? "callout ok" : "error" }, b.passed ? `All ${b.gates.length} gates passed.` : "A gate failed."),
    h("h2", {}, "Stages this run logged"), stageList(b.stages), h("h2", {}, `Gates (${b.gates.length})`),
    table(["Gate", "Result", "Detail"], b.gates.map((g) => [g.name, h("span", { class: g.ok ? "ok" : "bad" }, g.ok ? "pass" : "FAIL"), tidy(g.detail)])),
    h("div", { class: "row" }, button("Next stage: review outputs", () => go(run, "files"))));
}

async function resultsStep(run) {
  const r = await api("GET", `/runs/${run.id}/results`);
  const others = (await api("GET", "/runs")).filter((x) => x.id !== run.id && x.status === "done");
  const f = Object.fromEntries(["line", "column", "value"].map((k) => [k, h("input", { placeholder: k, size: k === "value" ? 14 : 10 })]));
  f.file = h("select", {}, ["fx_rates.csv", "tb_uk.csv", "tb_us.csv", "tb_in.csv", "intercompany.csv", "subledger_controls.csv"].map((n) => h("option", {}, n)));
  const name = h("input", { placeholder: "name for the new run" });
  const build = async () => {
    try {
      const n = await api("POST", `/runs/${run.id}/whatif`, { name: name.value, patches: [`${f.file.value}:${f.line.value}.${f.column.value}=${f.value.value}`] });
      go(n, "results");
    } catch (e) { fail(e); }
  };
  const other = h("select", {}, [h("option", { value: "" }, "choose a run")].concat(others.map((o) => h("option", { value: o.id }, `${o.name} (${o.id})`))));
  const holder = h("div");
  const compare = async () => {
    if (!other.value) return;
    try {
      const c = await api("GET", `/runs/${run.id}/compare/${other.value}`);
      holder.replaceChildren(h("h2", {}, "Input changes"), h("ul", {}, (c.input_changes.length ? c.input_changes : ["identical inputs"]).map((t) => h("li", {}, t))),
        h("h2", {}, "What each changed line feeds (1% nudge)"),
        table(["Line", "Figures that move"], Object.entries(c.impact).map(([t, m]) => [h("code", {}, t), Object.entries(m).map(([k, v]) => `${k}: ${amount(v.before)} → ${amount(v.after)}`).join("; ") || "none"])),
        h("h2", {}, "Figures that differ"), table(["Figure", "Other run", "This run"], c.figures.map((x) => [x.key, figureValue({ value: x.other }), figureValue({ value: x.this })])));
    } catch (e) { fail(e); }
  };
  show(...head(run, "Results"), h("h2", {}, "The 12 control figures"),
    figuresTable(r.figures),
    h("h2", {}, `Issues (${r.issues.length})`), ...issueGroups(r.cards, {}, () => {}),
    h("h2", {}, "What if an input changes?"), h("p", { class: "muted" }, "Builds a new run from a changed cell (line 1 is the header); this run is left as it is."),
    h("div", { class: "row" }, f.file, f.line, f.column, f.value, name, button("Build new run", build)),
    h("h2", {}, "Compare with another run"), h("div", { class: "row" }, other, button("Compare", compare, true)), holder,
    h("div", { class: "row" }, button("Back to done", () => go(run, "export"))));
}

// Done: the sign-off status, why it is a Draft if it is one, and the zip. The status is also written into the zip.
async function exportStep(run) {
  const s = await api("GET", `/runs/${run.id}/signoff`);
  const final = s.status === "Final";
  show(...head(run, "7 Done"), h("div", { class: final ? "callout ok" : "callout warn", role: "status" }, h("strong", {}, `${s.status}. `),
    final ? "Every problem is answered and every exported file is reviewed." : s.reasons.join(". ") + ". Go back to answer or review them, or download the Draft as it is."),
    table(["File", "Review"], s.files.map((f) => [h("code", {}, f.name), f.state === "reviewed" ? `Reviewed by ${f.reviewed_by}` : f.state === "stale" ? "Changed since reviewed" : "Not reviewed"])),
    h("div", { class: "row" }, h("a", { class: "btn", href: `/api/runs/${run.id}/export` }, `Download ${s.status} zip`),
      h("a", { class: "btn plain", href: `#/run/${run.id}/files` }, "Back to review outputs"),
      h("a", { class: "btn plain", href: `#/run/${run.id}/results` }, "Results, what-if and compare")),
    h("p", { class: "muted small" }, "The zip holds the exported files, the run manifest and signoff.json with this status and who reviewed each file."));
}

const STEP_VIEWS = { upload: uploadStep, scan: scanStep, review: reviewStep, outputs: outputsStep, build: buildStep, results: resultsStep, files: filesStep, export: exportStep };
