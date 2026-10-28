#!/usr/bin/env node
// Structural check for the interactive HTML reference pages.
//
//   node docs/html/check.mjs
//
// For each of peek.html / cng.html / acme.html it extracts the `render({ … })`
// data object from the last <script> block, evaluates it, and asserts:
//
//   (a) every PascalCase identifier referenced in a method `sig`, a field
//       `type`, a type `def`, an `extends`, a `ctor` or an `obtain` string is
//       either a documented service/model on the SAME page or a Python
//       builtin/typing/stdlib name — i.e. no dangling auto-link targets;
//   (b) every `extends` names a model on the same page, names are unique, and
//       a `kind:"type"`/`"union"` entry carries a `def`;
//   (c) the non-data portion of the three pages (everything outside the data
//       <script>) is byte-identical, except the per-page <h1> brand line.
//
// Exits non-zero (and lists every problem) when anything fails.

import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const PAGES = ["peek.html", "cng.html", "acme.html"];

// Names that may appear in a signature/type without being documented.
const ALLOWED = new Set([
  // Python builtins
  "None", "True", "False", "Exception", "BaseException", "ValueError",
  // typing / collections.abc / stdlib
  "Literal", "Mapping", "Sequence", "Any", "Union", "Final", "Self", "Protocol",
  "Optional", "Iterable", "Callable", "TypedDict", "Awaitable", "Coroutine",
  // stdlib modules/classes that are written with their module prefix
  "AsyncClient", // httpx.AsyncClient
]);

const PASCAL_RE = /\b[A-Z][a-z][A-Za-z0-9]*\b/g;
const DATA_MARKER_RE = /\/\* ---------- [A-Z]+ DATA ---------- \*\//;

const problems = [];
const fail = (page, msg) => problems.push(`${page}: ${msg}`);

function splitPage(page) {
  const html = readFileSync(join(here, page), "utf8");
  const open = html.lastIndexOf("<script>");
  const close = html.lastIndexOf("</script>");
  if (open < 0 || close < open) throw new Error(`${page}: cannot find the data <script> block`);
  return {
    shell: html.slice(0, open + "<script>".length) + html.slice(close),
    dataSrc: html.slice(open + "<script>".length, close),
  };
}

function evalData(page, src) {
  if (!DATA_MARKER_RE.test(src)) fail(page, "data <script> lacks the '/* ---------- X DATA ---------- */' marker");
  let captured = null;
  new Function("render", src)((d) => { captured = d; });
  if (!captured || !Array.isArray(captured.services) || !Array.isArray(captured.models)) {
    throw new Error(`${page}: render() was not called with {services, models}`);
  }
  return captured;
}

function checkPage(page, data) {
  const names = new Map(); // name -> where
  for (const s of data.services) {
    if (names.has(s.name)) fail(page, `duplicate name "${s.name}" (also ${names.get(s.name)})`);
    names.set(s.name, "service");
  }
  for (const m of data.models) {
    if (names.has(m.name)) fail(page, `duplicate name "${m.name}" (also ${names.get(m.name)})`);
    names.set(m.name, "model");
  }
  const modelNames = new Set(data.models.map((m) => m.name));

  const refs = []; // {text, where}
  for (const s of data.services) {
    if (s.ctor) refs.push({ text: s.ctor, where: `${s.name}.ctor` });
    if (s.obtain) refs.push({ text: s.obtain, where: `${s.name}.obtain` });
    for (const m of s.methods || []) {
      if (typeof m.sig !== "string" || !m.sig) fail(page, `${s.name}.${m.name} has no sig`);
      else refs.push({ text: m.sig, where: `${s.name}.${m.name}.sig` });
    }
  }
  for (const m of data.models) {
    if ((m.kind === "type" || m.kind === "union") && typeof m.def !== "string") {
      fail(page, `model "${m.name}" is kind:"${m.kind}" but has no def`);
    }
    if (m.extends) {
      refs.push({ text: m.extends, where: `${m.name}.extends` });
      if (!modelNames.has(m.extends)) fail(page, `model "${m.name}" extends undocumented "${m.extends}"`);
    }
    if (m.def) refs.push({ text: m.def, where: `${m.name}.def` });
    for (const f of m.fields || []) {
      if (typeof f.type !== "string") fail(page, `${m.name}.${f.name} has no type`);
      else refs.push({ text: f.type, where: `${m.name}.${f.name}.type` });
    }
  }

  const dangling = new Map(); // name -> [where]
  for (const { text, where } of refs) {
    // Drop quoted literals ("ACTIVITY", "withBookings", …) and HTML entities before scanning.
    const bare = text.replace(/"(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*'/g, '""').replace(/&[a-z]+;/g, " ");
    for (const id of bare.match(PASCAL_RE) || []) {
      if (names.has(id) || ALLOWED.has(id)) continue;
      if (!dangling.has(id)) dangling.set(id, []);
      dangling.get(id).push(where);
    }
  }
  for (const [id, wheres] of dangling) {
    fail(page, `dangling type reference "${id}" in ${[...new Set(wheres)].join(", ")}`);
  }
  return { services: data.services.length, models: data.models.length, refs: refs.length };
}

function normalizeShell(shell) {
  return shell.replace(/<h1>[^<]*<\/h1>/, "<h1></h1>");
}

const shells = {};
for (const page of PAGES) {
  try {
    const { shell, dataSrc } = splitPage(page);
    shells[page] = normalizeShell(shell);
    const data = evalData(page, dataSrc);
    const stats = checkPage(page, data);
    console.log(`${page}: ${stats.services} services, ${stats.models} models, ${stats.refs} linkified strings scanned`);
  } catch (e) {
    fail(page, e.message);
  }
}

for (const page of PAGES.slice(1)) {
  if (shells[page] !== undefined && shells[PAGES[0]] !== undefined && shells[page] !== shells[PAGES[0]]) {
    const a = shells[PAGES[0]].split("\n"), b = shells[page].split("\n");
    const i = a.findIndex((line, idx) => line !== b[idx]);
    fail(page, `non-data portion differs from ${PAGES[0]} (first difference at shell line ${i + 1}: ${JSON.stringify(a[i])} vs ${JSON.stringify(b[i])})`);
  }
}

if (problems.length) {
  console.error(`\n${problems.length} problem(s):`);
  for (const p of problems) console.error("  - " + p);
  process.exit(1);
}
console.log("OK: no dangling type references; shells identical outside the data object (and the <h1> brand line).");
