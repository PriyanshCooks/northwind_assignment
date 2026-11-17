// Review UI: hash router, API helper and the runs list. Everything from the server is put on the page with
// text nodes (never as HTML), so uploaded text is shown as data and cannot run as script.
const STEPS = [["upload", "1 Upload"], ["review", "2 Review"], ["outputs", "3 Choose outputs"],
               ["build", "4 Build"], ["results", "5 Results"], ["export", "6 Export"]];
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

function show(...nodes) { view.replaceChildren(...nodes); }
function fail(error) { view.prepend(h("div", { class: "error" }, String(error.message || error))); }
function table(head, rows) {
  return h("table", {}, h("thead", {}, h("tr", {}, head.map((t) => h("th", {}, t)))),
           h("tbody", {}, rows.map((r) => h("tr", {}, r.map((c) => h("td", {}, c))))));
}
function when(text) { return new Date(text).toLocaleString(); }
function shown(v) { return v === null ? "null" : typeof v === "object" ? JSON.stringify(v) : String(v); }

function drawStepper(run, step) {
  stepper.replaceChildren(...(run ? STEPS.map(([key, label]) =>
    h("a", { href: `#/run/${run.id}/${key}`, class: key === step ? "here" : "" }, label)) : []));
}

function nextStep(run) {
  return { new: "upload", awaiting_review: "review", done: "results" }[run.status] || "review";
}

async function runsList() {
  drawStepper(null);
  const runs = await api("GET", "/runs");
  const name = h("input", { placeholder: "run name", maxlength: 60 });
  const sample = h("input", { type: "checkbox" });
  const create = async () => {
    try {
      const run = await api("POST", "/runs", { name: name.value, use_sample: sample.checked });
      location.hash = `#/run/${run.id}/upload`;
    } catch (e) { fail(e); }
  };
  show(h("h1", {}, "Runs"),
    h("div", { class: "row" }, name, h("label", {}, sample, " start with the supplied sample files"),
      h("button", { onclick: create }, "New run")),
    runs.length ? table(["Name", "Id", "Status", "Created", "Based on", ""], runs.map((r) => [
      r.name, h("code", {}, r.id), h("span", { class: "tag" }, r.status), when(r.created), r.parent || "",
      h("a", { class: "btn plain", href: `#/run/${r.id}/${nextStep(r)}` },
        r.status === "awaiting_review" ? "Resume" : "Open")])) : h("p", { class: "muted" }, "No runs yet."));
}

async function route() {
  const [, kind, id, step] = location.hash.split("/");
  try {
    if (kind !== "run") return await runsList();
    const run = await api("GET", `/runs/${id}`);
    const chosen = STEPS.some(([k]) => k === step) ? step : nextStep(run);
    drawStepper(run, chosen);
    await STEP_VIEWS[chosen](run);
  } catch (e) { show(h("div", { class: "error" }, String(e.message || e)), h("a", { href: "#/" }, "Back to runs")); }
}
window.addEventListener("hashchange", route);
