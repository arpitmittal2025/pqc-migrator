/* PQC Migrator — front end. Talks to /api/analyze and renders the pipeline. */

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g,
  (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

let SAMPLES = [];
let selected = "app_rsa";
let lastResult = null;

/* ------------------------------------------------------------- helpers */

async function api(payload) {
  const response = await fetch("/api/analyze", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  let body;
  try {
    body = await response.json();
  } catch {
    throw new Error(`Server returned ${response.status} without JSON.`);
  }
  if (!response.ok || body.ok === false) {
    throw new Error(body.error || `Request failed (${response.status}).`);
  }
  return body;
}

function table(headers, rows, emptyText) {
  if (!rows.length) return `<p class="empty">${esc(emptyText)}</p>`;
  return `<div class="scroll"><table><thead><tr>${
    headers.map((h) => `<th>${esc(h)}</th>`).join("")
  }</tr></thead><tbody>${
    rows.map((r) => `<tr>${r.map((c) => `<td>${c}</td>`).join("")}</tr>`).join("")
  }</tbody></table></div>`;
}

const purposeTag = (p) =>
  `<span class="tag ${p === "signature" ? "sig" : "kem"}">${esc(p)}</span>`;

/* ----------------------------------------------------------- rendering */

function renderSamples() {
  $("samples").innerHTML = SAMPLES.map((s) => `
    <button class="sample" data-id="${esc(s.id)}" aria-pressed="${s.id === selected}">
      <div class="t">${esc(s.title)}</div>
      <div class="b">${esc(s.blurb)}</div>
      <div class="e">${esc(s.expect)}</div>
    </button>`).join("");

  for (const button of document.querySelectorAll(".sample")) {
    button.addEventListener("click", () => {
      selected = button.dataset.id;
      for (const other of document.querySelectorAll(".sample")) {
        other.setAttribute("aria-pressed", String(other === button));
      }
    });
  }
}

function renderStages(data) {
  const checks = Object.values(data.verification);
  const passed = checks.filter(Boolean).length;
  const review = data.stats.manual_review || 0;

  $("sFindings").textContent = data.findings.length;
  $("sMigrated").textContent =
    `${data.stats.migrated_findings}/${data.stats.findings}`;
  $("sChecks").textContent = `${passed}/${checks.length}`;
  $("sReview").textContent = review;
  $("sElapsed").textContent = `${(data.elapsed_ms / 1000).toFixed(1)}s`;

  $("sMigrated").parentElement.className =
    "stage " + (data.stats.migrated_findings === data.stats.findings && data.stats.findings ? "ok" : "warnish");
  $("sChecks").parentElement.className =
    "stage " + (passed === checks.length ? "ok" : "bad");
  $("sReview").parentElement.className = "stage " + (review ? "warnish" : "ok");
  $("stages").hidden = false;
}

function renderFindings(data) {
  const rows = data.findings.map((f) => [
    `<span class="mono">${esc(f.file)}</span>`,
    `<span class="num">${f.line}</span>`,
    `<strong>${esc(f.algorithm.toUpperCase())}</strong>`,
    purposeTag(f.purpose),
    `<code>${esc(f.matched)}</code>`,
    esc(f.library),
  ]);
  const deps = Object.entries(data.analysis.vulnerable_dependencies || {})
    .map(([k, v]) => `<li><code>${esc(k)}</code> — ${esc(v)}</li>`).join("");

  $("pFindings").innerHTML = `
    <p class="hint" style="margin-top:0">
      Every <code>.py</code> file is parsed into a syntax tree and matched against the
      pattern index. The <em>purpose</em> column is inferred from how the key is used in the
      rest of the module — that is what decides which NIST standard applies.
    </p>
    ${table(["File", "Line", "Algorithm", "Purpose", "Construct", "Library"], rows,
            "No classical public-key cryptography detected.")}
    ${deps ? `<p class="hint" style="margin-top:.9rem">Dependencies introducing classical crypto:</p><ul class="hint">${deps}</ul>` : ""}`;
}

function renderRecommend(data) {
  const rows = data.recommendations.map((r) => [
    `<code>${esc(r.finding.matched)}</code>`,
    `<span class="mono">${esc(r.finding.file)}:${r.finding.line}</span>`,
    `<strong>${esc(r.pqc_algorithm)}</strong>`,
    esc(r.nist_standard),
    `<span class="num">${r.nist_level}</span>`,
  ]);
  const why = data.recommendations.length
    ? `<details style="margin-top:.9rem"><summary class="hint" style="cursor:pointer">Why each algorithm was chosen</summary>
       <ul class="hint">${data.recommendations.map((r) =>
         `<li><code>${esc(r.finding.matched)}</code> → <strong>${esc(r.pqc_algorithm)}</strong> — ${esc(r.rationale)}</li>`
       ).join("")}</ul></details>`
    : "";

  $("pRecommend").innerHTML = `
    <p class="hint" style="margin-top:0">
      Context: NIST category <strong>${data.context.security_level}</strong>,
      preferred signature family <strong>${esc(data.context.prefer_signature_scheme)}</strong>.
      Purpose selects the family, the category selects the parameter set, and strength
      signals in the original code can raise it.
    </p>
    ${table(["Construct", "Location", "PQC algorithm", "Standard", "Level"], rows,
            "Nothing to recommend.")}
    ${why}`;
}

function highlight(source) {
  return esc(source)
    .split("\n")
    .map((line) => {
      const isComment = /^\s*#/.test(line);
      const changed = /pqc_shim|ML-KEM|ML-DSA|SLH-DSA|TODO\(/.test(line);
      if (isComment) return `<span class="cm">${line || " "}</span>`;
      return changed ? `<span class="hl">${line || " "}</span>` : (line || " ");
    })
    .join("\n");
}

function renderMigrate(data) {
  const names = Object.keys(data.migrated_files);
  const sampleFiles = (SAMPLES.find((s) => s.id === selected) || {}).files || {};

  const notes = data.migrations.filter((m) => m.manual_review || !m.changed);
  const noteHtml = notes.length
    ? `<div class="note"><strong>Needs attention.</strong><ul style="margin:.4rem 0 0;padding-left:1.1rem">${
        notes.map((m) => `<li><span class="mono">${esc(m.migrated_file)}</span> — ${esc(m.notes)}</li>`).join("")
      }</ul></div>`
    : "";

  const rows = data.migrations.map((m) => [
    `<span class="mono">${esc(m.original_file)}</span>`,
    m.changed ? '<span class="tag pass">migrated</span>' : '<span class="tag fail">unchanged</span>',
    m.manual_review ? '<span class="tag review">manual review</span>' : "—",
    esc((m.rules_applied || []).join(", ") || "—"),
  ]);

  $("pMigrate").innerHTML = `
    <p class="hint" style="margin-top:0">
      The original files are never modified — these are rewritten copies. Highlighted lines
      are the ones the rules changed.
    </p>
    ${noteHtml}
    <div class="code-head">
      <label for="fileSel" class="hint" style="margin:0">File</label>
      <select id="fileSel">${names.map((n) => `<option>${esc(n)}</option>`).join("")}</select>
    </div>
    <div class="diff">
      <div class="code-col"><div class="lbl">Before — original</div><pre class="code" id="codeBefore"></pre></div>
      <div class="code-col"><div class="lbl">After — migrated</div><pre class="code" id="codeAfter"></pre></div>
    </div>
    <h3 style="margin-top:1.4rem">Rules applied</h3>
    ${table(["File", "Result", "Review", "Rules"], rows, "Nothing migrated.")}`;

  const show = (name) => {
    $("codeBefore").innerHTML = highlight(sampleFiles[name] ?? "(original not shown for pasted code)");
    $("codeAfter").innerHTML = highlight(data.migrated_files[name] ?? "");
  };
  if (names.length) {
    show(names[0]);
    $("fileSel").addEventListener("change", (e) => show(e.target.value));
  }
}

function renderVerify(data) {
  const entries = Object.entries(data.verification);
  const checks = entries.map(([name, ok]) => `
    <div class="check">
      <span class="tag ${ok ? "pass" : "fail"}">${ok ? "PASS" : "FAIL"}</span>
      <span class="name">${esc(name)}</span>
    </div>`).join("");

  const execution = data.execution || {};
  let execHtml = "";
  if (execution.attempted) {
    execHtml = `<div class="note" style="border-left-color:var(--${execution.passed ? "pass" : "fail"})">
      <strong>${execution.passed ? "The migrated program ran successfully." : "The migrated program failed to run."}</strong>
      ${execution.output ? `<pre class="code" style="margin-top:.5rem;max-height:160px">${esc(execution.output)}</pre>` : ""}
    </div>`;
  } else if (execution.reason) {
    execHtml = `<div class="note">${esc(execution.reason)}</div>`;
  }

  $("pVerify").innerHTML = `
    <p class="hint" style="margin-top:0">
      Three of these are <em>negative</em> tests — a tampered message, a wrong key and a
      foreign decapsulation key must all be rejected. A stage that only confirms success
      cannot tell working cryptography from a stub that always returns true.
    </p>
    ${execHtml}
    <div class="checks">${checks || '<p class="empty">No checks run.</p>'}</div>`;
}

function renderBench(data) {
  const entries = Object.entries(data.benchmark).filter(([, v]) => !v.error);
  if (!entries.length) {
    $("pBench").innerHTML = '<p class="empty">Benchmark not run.</p>';
    return;
  }

  const rows = entries.map(([name, d]) => [
    `<strong>${esc(name)}</strong>`,
    `<span class="tag ${d.kind === "pqc" ? "kem" : "sig"}">${esc(d.kind)}</span>`,
    esc(d.standard || "—"),
    `<span class="num">${d.keygen_ms}</span>`,
    `${esc(d.operation)} <span class="num">${d.op_ms}</span>`,
    `<span class="num">${(d.pubkey_bytes || 0).toLocaleString()}</span>`,
    `<span class="num">${(d.sig_or_ct_bytes || 0).toLocaleString()}</span>`,
  ]);

  const maxKey = Math.max(...entries.map(([, d]) => d.pubkey_bytes || 0));
  const bars = entries.map(([name, d]) => `
    <div class="bar-row">
      <span>${esc(name)}</span>
      <span class="bar-track"><span class="bar-fill ${d.kind === "classical" ? "classical" : ""}"
        style="width:${Math.max(2, ((d.pubkey_bytes || 0) / maxKey) * 100)}%"></span></span>
      <span class="val">${(d.pubkey_bytes || 0).toLocaleString()} B</span>
    </div>`).join("");

  $("pBench").innerHTML = `
    <p class="hint" style="margin-top:0">
      Measured on the server handling this request, medians over repeated runs — nothing
      stored. Sizes are fixed by the standards; timings depend on the active backend
      (<code>${esc(data.backend.backend)}</code>).
    </p>
    ${table(["Algorithm", "Kind", "Standard", "Keygen ms", "Primary op", "Public key B", "Sig/CT B"],
            rows, "No benchmark.")}
    <h3 style="margin-top:1.4rem">Public key size</h3>
    <div class="bars">${bars}</div>`;
}

/* ------------------------------------------------------------- actions */

function selectTab(id) {
  for (const tab of document.querySelectorAll(".tab")) {
    const on = tab.dataset.panel === id;
    tab.setAttribute("aria-selected", String(on));
    $(tab.dataset.panel).hidden = !on;
  }
}

async function run() {
  const button = $("run");
  const code = $("code").value.trim();
  button.disabled = true;
  button.innerHTML = '<span class="spinner"></span>Running…';
  $("error").hidden = true;

  try {
    const payload = {
      security_level: Number($("level").value),
      signature_scheme: $("scheme").value,
    };
    if (code) {
      payload.code = code;
      payload.filename = $("filename").value || "app.py";
    } else {
      payload.sample = selected;
    }

    const data = await api(payload);
    lastResult = data;

    renderStages(data);
    renderFindings(data);
    renderRecommend(data);
    renderMigrate(data);
    renderVerify(data);
    renderBench(data);

    $("placeholder").hidden = true;
    $("results").hidden = false;
    selectTab("pFindings");
  } catch (err) {
    $("error").innerHTML = `<div class="err"><strong>Could not run the pipeline.</strong> ${esc(err.message)}</div>`;
    $("error").hidden = false;
  } finally {
    button.disabled = false;
    button.textContent = "Run the pipeline";
  }
}

/* --------------------------------------------------------------- start */

$("level").addEventListener("input", (e) => { $("levelOut").value = e.target.value; });
$("run").addEventListener("click", run);
$("tabs").addEventListener("click", (e) => {
  const tab = e.target.closest(".tab");
  if (tab) selectTab(tab.dataset.panel);
});

(async function init() {
  try {
    const info = await api({ action: "backend" });
    $("backendPill").textContent = `backend: ${info.backend} · python ${info.python}`;
    $("backendPill").title = info.note;
  } catch {
    $("backendPill").textContent = "backend unavailable";
    $("backendPill").classList.remove("live");
  }
  try {
    const data = await api({ action: "samples" });
    SAMPLES = data.samples || [];
    renderSamples();
  } catch (err) {
    $("samples").innerHTML = `<div class="err">Could not load samples: ${esc(err.message)}</div>`;
  }
})();
