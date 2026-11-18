// Review UI: hash router, API helper and the runs list. Everything from the server is put on the page with
// text nodes (never as HTML), so uploaded text is shown as data and cannot run as script.
const STEPS = [["upload", "1 Upload"], ["scan", "2 Scan"], ["review", "3 Review inputs"], ["build", "4 Generate"],
               ["outputs", "5 Choose outputs"], ["results", "6 Results"], ["files", "7 Output files"], ["export", "8 Export"]];
const view = document.getElementById("view");
const stepper = document.getElementById("stepper");

function h(tag, attrs = {}, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (v === true) el.setAttribute(k, "");
    else if (v !== false && v != null) el.setAttribute(k, v);
  }
  for (const kid of kids.flat()) if (kid != null) el.append(kid.nodeType ? kid : String(kid));
  return el;
}

async function api(method, path, body, raw) {
  const init = { method, headers: {} };
  if (raw !== undefined) init.body = raw;
  else if (body !== undefined) { init.body = JSON.stringify(body); init.headers["Content-Type"] = "application/json"; }
  const res = await fetch("/api" + path, init);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail || res.status));
  return data;
}

function show(...nodes) { view.replaceChildren(...nodes.filter((n) => n != null)); }
function fail(error) { view.prepend(h("div", { class: "error" }, String(error.message || error))); }
function table(head, rows) {
  return h("table", {}, h("thead", {}, h("tr", {}, head.map((t) => h("th", {}, t)))),
           h("tbody", {}, rows.map((r) => h("tr", {}, r.map((c) => h("td", {}, c))))));
}
function when(text) { return new Date(text).toLocaleString(); }

const STATUS = { new: "Not analysed", awaiting_review: "Waiting for a decision", done: "Finished", blocked: "Blocked" };

// One state per step, from what the run already holds: nothing here is a guess about work not done.
function stepState(run, key, step) {
  const finished = run.status === "done", analysed = run.status !== "new", output = finished || Boolean(run.built);
  if (key === step) return "current";
  if (run.blocked && key === "review") return "blocked";
  const done = { upload: analysed, scan: analysed, review: finished, outputs: Boolean(run.outputs), build: output, results: false, files: false, export: false }[key];
  if (done) return "done";
  if (key === "review" && run.status === "awaiting_review") return "blocked";
  const locked = { scan: !analysed, review: !analysed, build: !analysed, outputs: !output, results: !output, files: !output, export: !output }[key];
  return locked ? "locked" : "todo";
}
const STATE_TEXT = { done: "Done", current: "Current", blocked: "Needs you", locked: "Not yet", todo: "Ready" };

function drawStepper(run, step) {
  const runbar = document.getElementById("runbar");
  if (!run) { stepper.replaceChildren(); runbar.replaceChildren(h("span", {}, "Review a consolidation run step by step")); return; }
  const at = STEPS.findIndex(([k]) => k === step);
  runbar.replaceChildren(h("strong", {}, run.name), h("code", {}, run.id),
    h("span", { class: "stage" }, `Stage ${at + 1} of ${STEPS.length}: ${STEPS[at][1].slice(2)}`),
    h("span", { class: "tag" }, STATUS[run.blocked ? "blocked" : run.status] || run.status));
  stepper.replaceChildren(...STEPS.map(([key, label], i) => {
    const state = stepState(run, key, step);
    const mark = state === "done" ? "\u2713" : state === "blocked" ? "!" : String(i + 1);
    return h(state === "locked" ? "span" : "a", { href: state === "locked" ? null : `#/run/${run.id}/${key}`, class: `item ${state}`,
      "aria-current": state === "current" ? "step" : null },
      h("span", { class: "dot", "aria-hidden": "true" }, mark),
      h("span", { title: STATE_TEXT[state] }, label.slice(2)));
  }));
}

function nextStep(run) {
  return { new: "upload", awaiting_review: "review", done: "results" }[run.status] || "review";
}

// Stage 0, Home: continue a run by its id, or create a new one. The list of runs stays below for a run you did not note down.
async function runsList() {
  drawStepper(null);
  const showArchived = location.hash === "#/archived";
  const runs = await api("GET", showArchived ? "/runs?archived=true" : "/runs");
  const keep = (r, what) => async () => { try { await api("POST", `/runs/${r.id}/${what}`); await route(); } catch (e) { fail(e); } };
  const problem = h("div", { class: "error", role: "alert", hidden: true });
  const say = (text) => { problem.textContent = text; problem.hidden = !text; };
  const runId = h("input", { placeholder: "r20261118-101500-ab12", size: 26, "aria-label": "Run id", autocomplete: "off" });
  const open = async () => {
    const id = runId.value.trim();
    if (!id) return say("Enter a run id first.");
    try { const run = await api("GET", `/runs/${encodeURIComponent(id)}`); say(""); location.hash = `#/run/${run.id}/${nextStep(run)}`; }
    catch (e) { say(`No run with the id ${id} was found.`); }
  };
  const name = h("input", { placeholder: "run name", maxlength: 60, "aria-label": "Run name" });
  const sample = h("input", { type: "checkbox" });
  const create = async () => {
    try { const run = await api("POST", "/runs", { name: name.value, use_sample: sample.checked }); location.hash = `#/run/${run.id}/upload`; }
    catch (e) { fail(e); }
  };
  show(h("h1", {}, "Northwind consolidation review"),
    h("div", { class: "home" },
      h("section", { class: "card" }, h("h2", {}, "Continue a run"), h("p", { class: "muted" }, "Paste the id of a run you started before."),
        h("div", { class: "row" }, runId, h("button", { onclick: open }, "Open run"))),
      h("section", { class: "card" }, h("h2", {}, "Create a new run"),
        h("div", { class: "row" }, name), h("label", {}, sample, " start with the supplied sample files"),
        h("div", { class: "row" }, h("button", { onclick: create }, "Create new run")))),
    problem,
    h("h2", {}, showArchived ? "Archived runs" : "Recent runs"),
    runs.length ? table(["Name", "Id", "Status", "Created", "Based on", ""], runs.map((r) => [
      r.name, h("code", {}, r.id), h("span", { class: "tag" }, r.status), when(r.created), r.parent || "",
      h("span", { class: "row" }, h("a", { class: "btn plain", href: `#/run/${r.id}/${nextStep(r)}` },
        r.status === "awaiting_review" ? "Resume" : "Open"),
      h("button", { class: "plain", onclick: keep(r, showArchived ? "restore" : "archive") }, showArchived ? "Restore" : "Archive"))]))
      : h("p", { class: "muted" }, showArchived ? "No archived runs." : "No runs yet."),
    h("p", {}, h("a", { href: showArchived ? "#/" : "#/archived" }, showArchived ? "Back to runs" : "Show archived runs")));
}

// A step that needs a finished run says why it cannot open yet and what to do, instead of showing an error.
function holdBack(run, step) {
  if (["upload", "scan", "review"].includes(step) || run.status === "done" || run.built || (step === "build" && run.status !== "new")) return null;
  const to = (key, label) => h("a", { class: "btn", href: `#/run/${run.id}/${key}` }, label);
  if (run.blocked) return [h("h1", {}, "This run is blocked"), h("div", { class: "callout bad" }, run.blocked), to("review", "Open the review")];
  if (run.status === "awaiting_review") {
    return [h("h1", {}, "This run has no output yet"), h("div", { class: "callout warn" }, `${run.open_items.length} item(s) are still open. ` +
      "Generate the output from the review: it will be a Draft and the open items stay marked as problems."), to("review", "Go to the review")];
  }
  return [h("h1", {}, "This run has not been analysed"), h("div", { class: "callout" }, "Upload the 15 files, or start from the sample, then analyse them."), to("upload", "Go to upload")];
}

// Anything still unanswered keeps the output a Draft, and the pages that show or export it say so at the top.
async function draftBanner(run) {
  const left = await api("GET", `/runs/${run.id}/unanswered`);
  if (!left.draft) return;
  const count = left.problems;
  view.prepend(h("div", { class: "callout warn", role: "status" }, h("strong", {}, "Draft. "),
    `${count} problem(s) are still unanswered, so this output is not final. `, h("a", { href: `#/run/${run.id}/review` }, "Go to the review")));
}

async function route() {
  const [, kind, id, step] = location.hash.split("/");
  try {
    if (kind !== "run") return await runsList();
    const run = await api("GET", `/runs/${id}`);
    const chosen = STEPS.some(([k]) => k === step) ? step : nextStep(run);
    drawStepper(run, chosen);
    const waiting = holdBack(run, chosen);
    if (waiting) return show(...waiting);
    show(h("p", { role: "status", class: "muted" }, "Loading…"));
    await STEP_VIEWS[chosen](run);
    if (["outputs", "results", "files", "export"].includes(chosen)) await draftBanner(run);
  } catch (e) {
    show(h("div", { class: "error", role: "alert" }, String(e.message || e)),
      h("div", { class: "row" }, h("button", { onclick: route }, "Try again"), h("a", { class: "btn plain", href: "#/" }, "Back to runs")));
  }
}
window.addEventListener("hashchange", route);
