// The six step views. Each reads from the API and draws; no number is calculated here.
const head = (run, title) => [h("h1", {}, title), h("p", { class: "muted" }, run.name + " · ", h("code", {}, run.id))];
const go = (run, step) => { location.hash = `#/run/${run.id}/${step}`; };
// Display only: the engine's gate detail carries Decimal reprs and 40-digit differences; show them readably.
const tidy = (t) => t.replace(/Decimal\('([^']+)'\)/g, "$1").replace(/(\d+\.\d{6})\d+/g, "$1").replace(/-?\d+(\.\d+)?E-\d{2,}/g, "0");
const button = (label, onclick, plain) => h("button", { onclick, class: plain ? "plain" : "" }, label);

async function uploadStep(run) {
  const rows = (files) => table(["File", "State", "Contract"], files.map((f) => [h("code", {}, f.name),
    f.present && !f.error ? h("span", { class: "ok" }, `ok (${f.bytes} bytes)`) :
      h("span", { class: "bad" }, f.present ? "rejected" : "missing"), f.error || ""]));
  const input = h("input", { type: "file", multiple: true });
  const upload = async () => {
    const results = [];
    for (const file of input.files) {
      try {
        const r = await api("PUT", `/runs/${run.id}/files/${encodeURIComponent(file.name)}`, undefined, await file.arrayBuffer());
        if (!r.stored) results.push(`${file.name}: ${r.error}`);
      } catch (e) { results.push(`${file.name}: ${e.message}`); }
    }
    await uploadStep(run);
    results.forEach((t) => view.prepend(h("div", { class: "error" }, t)));
  };
  const fresh = await api("GET", `/runs/${run.id}`);
  const ready = fresh.files.every((f) => f.present && !f.error);
  const next = async () => { try { await api("POST", `/runs/${run.id}/analyse`); go(run, "review"); } catch (e) { fail(e); } };
  show(...head(run, "1 Upload"), h("div", { class: "callout" }, "Only the 15 expected file names are accepted, up to 1 MB each. " +
    "A file that breaks its contract is refused and the reason is shown on its row."),
    h("div", { class: "row" }, input, button("Upload", upload)), rows(fresh.files),
    h("div", { class: "row" }, h("button", { onclick: next, disabled: !ready }, "Analyse and go to Review")));
}

async function reviewStep(run) {
  if (run.status === "new") {
    return show(...head(run, "2 Review"), h("p", {}, "This run has not been analysed yet."),
      button("Analyse", async () => { try { await api("POST", `/runs/${run.id}/analyse`); await route(); } catch (e) { fail(e); } }));
  }
  const rv = await api("GET", `/runs/${run.id}/review`);
  const marks = {};
  const approver = h("input", { placeholder: "your name", maxlength: 60 });
  const waiting = rv.queue.filter((q) => rv.open_items.includes(q.key));
  const choose = (q) => h("select", { onchange: (e) => { marks[q.key] = e.target.value; } },
    ["", "approve", "reject"].map((v) => h("option", { value: v }, v || "undecided")));
  const send = async () => {
    const decisions = Object.fromEntries(Object.entries(marks).filter(([, v]) => v));
    try { await api("POST", `/runs/${run.id}/decisions`, { approver: approver.value, decisions }); await route(); }
    catch (e) { fail(e); }
  };
  const advice = rv.advice.map((a) => [a.kind, a.unit, a.recorded ? "recorded model answer" : "not recorded (rule fallback)",
    a.verified.join(", "), a.unverified.join(", "), a.dropped.map((d) => `${d.claim}: ${d.why}`).join("; "), a.missed.join(", ")]);
  show(...head(run, "2 Review"), h("p", {}, "Status: ", h("span", { class: "tag" }, run.status)),
    waiting.length ? h("div", {}, h("h2", {}, "Waiting for a decision"),
      table(["Item", "State", "Reason", "Decision"], waiting.map((q) => [h("code", {}, q.key), q.state, q.reason, choose(q)])),
      h("div", { class: "row" }, approver, button("Submit decisions", send))) :
      h("div", { class: "callout" }, "Nothing is waiting for a decision."),
    h("h2", {}, `Findings (${rv.findings.length})`),
    table(["Code", "Severity", "Where", "Claim", "Action"], rv.findings.map((f) =>
      [f.code, f.severity, `${f.file}:${f.line ?? ""}`, f.claim, f.action])),
    h("h2", {}, "Journal dispositions"),
    table(["Journal", "Disposition", "Reasons"], rv.dispositions.map((d) => [d.journal_id, d.status, d.reasons.join("; ")])),
    h("h2", {}, "Recorded AI advice"), h("p", { class: "muted" }, "Advice only: it changes no figure. Claims the packet does not " +
      "support are dropped and shown here. No model is called from this page."),
    table(["Kind", "Unit", "Source", "Verified", "Unverified", "Dropped claims", "Model missed"], advice),
    h("div", { class: "row" }, button("Next: choose outputs", () => go(run, "outputs"))));
}

async function outputsStep(run) {
  const out = await api("GET", `/runs/${run.id}/outputs`);
  const picked = new Set(out.chosen || out.available.map((o) => o.name));
  const boxes = out.available.map((o) => h("input", { type: "checkbox", checked: picked.has(o.name), disabled: o.required,
    onchange: (e) => (e.target.checked ? picked.add(o.name) : picked.delete(o.name)) }));
  const save = async () => { try { await api("PUT", `/runs/${run.id}/outputs`, { files: [...picked] }); go(run, "build"); } catch (e) { fail(e); } };
  show(...head(run, "3 Choose outputs"), h("p", { class: "muted" }, "The run manifest is always included."),
    table(["", "File", "Bytes"], out.available.map((o, i) => [boxes[i], h("code", {}, o.name), o.bytes])),
    h("div", { class: "row" }, button("Save and build", save)));
}

async function buildStep(run) {
  const b = await api("POST", `/runs/${run.id}/build`);
  show(...head(run, "4 Build"), h("div", { class: b.passed ? "callout ok" : "error" },
    b.passed ? `All ${b.gates.length} gates passed.` : "A gate failed" + (b.blocked ? `: ${b.blocked}` : ".")),
    table(["Gate", "Result", "Detail"], b.gates.map((g) => [g.name, h("span", { class: g.ok ? "ok" : "bad" }, g.ok ? "pass" : "FAIL"), tidy(g.detail)])),
    h("div", { class: "row" }, button("Next: results", () => go(run, "results"))));
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
        table(["Line", "Figures that move"], Object.entries(c.impact).map(([t, m]) => [h("code", {}, t), Object.entries(m).map(([k, v]) => `${k}: ${v.before} → ${v.after}`).join("; ") || "none"])),
        h("h2", {}, "Figures that differ"), table(["Figure", "Other run", "This run"], c.figures.map((x) => [x.key, shown(x.other), shown(x.this)])));
    } catch (e) { fail(e); }
  };
  show(...head(run, "5 Results"), h("h2", {}, "The 12 control figures"),
    table(["Figure", "Value", "Status", "Why / open items"], r.figures.map((x) => [x.key, shown(x.value),
      h("span", { class: x.status }, x.status), x.reason || (x.open_items || []).join("; ")])),
    h("h2", {}, `Issues (${r.issues.length})`),
    table(["Code", "Severity", "Where", "Action", "Claim"], r.issues.map((i) => [i.code, i.severity, `${i.file}:${i.line ?? ""}`, i.action, i.claim])),
    h("h2", {}, "What if an input changes?"), h("p", { class: "muted" }, "Builds a new run from a changed cell (line 1 is the header); this run is left as it is."),
    h("div", { class: "row" }, f.file, f.line, f.column, f.value, name, button("Build new run", build)),
    h("h2", {}, "Compare with another run"), h("div", { class: "row" }, other, button("Compare", compare, true)), holder,
    h("div", { class: "row" }, button("Next: export", () => go(run, "export"))));
}

async function exportStep(run) {
  const out = await api("GET", `/runs/${run.id}/outputs`);
  const names = out.chosen ? [...out.chosen, "run_manifest.json"] : out.available.map((o) => o.name);
  show(...head(run, "6 Export"), h("p", {}, "A zip of the chosen files plus the run manifest:"),
    h("ul", {}, [...new Set(names)].map((n) => h("li", {}, h("code", {}, n)))),
    h("a", { class: "btn", href: `/api/runs/${run.id}/export` }, "Download zip"));
}

const STEP_VIEWS = { upload: uploadStep, review: reviewStep, outputs: outputsStep, build: buildStep, results: resultsStep, export: exportStep };
