/**
 * Generates the interactive HTML changelog (`docs/html/changelog.html`) from the
 * consumer-facing `changelog.md`, so the HTML reference always mirrors the
 * markdown source.
 *
 * `changelog.md` is the single source of truth; this script renders its subset
 * of Markdown (headings, horizontal rules, bold, inline code, links, and up to
 * two levels of bullet lists) into a self-contained page that shares the look of
 * the other `docs/html/*` pages (left-nav, filter, light/dark toggle) and works
 * over `file://` (everything is inlined — no runtime fetch).
 *
 * Usage:
 *   node scripts/build-changelog-html.mjs           # (re)write docs/html/changelog.html
 *   node scripts/build-changelog-html.mjs --check    # exit 1 if the file is out of date
 *
 * A pytest drift guard (`tests/test_changelog_html.py`) runs this script with
 * `--check` and fails if the committed HTML differs from a fresh render, so
 * `pytest` catches a stale file before a commit. Vendored unchanged (apart from
 * the branding) from `@peektravel/app-utilities`.
 */
import { readFileSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const CHANGELOG_MD = join(HERE, '..', 'changelog.md');
const CHANGELOG_HTML = join(HERE, '..', 'docs', 'html', 'changelog.html');

const TAG_KINDS = ['breaking', 'fix', 'additive', 'deprecated'];

function escapeHtml(s) {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

/** Render a single line of inline Markdown (code, links, bold, tag badges). */
function renderInline(text) {
  const codes = [];
  // Pull out code spans first — behind a Private-Use-Area sentinel that cannot
  // occur in the source — so their contents are never treated as markup.
  let out = text.replace(/`([^`]+)`/g, (_m, c) => {
    codes.push(c);
    return '\uE000' + (codes.length - 1) + '\uE000';
  });
  out = escapeHtml(out);
  // Links: [text](url)
  out = out.replace(
    /\[([^\]]+)\]\(([^)]+)\)/g,
    (_m, label, url) =>
      '<a href="' + encodeURI(url) + '" target="_blank" rel="noopener">' + label + '</a>',
  );
  // Bold: **text**
  out = out.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
  // Restore code spans — a `[breaking]`/`[fix]`/… token becomes a colored badge.
  out = out.replace(/\uE000(\d+)\uE000/g, (_m, i) => {
    const raw = codes[Number(i)];
    const tag = raw.match(/^\[(breaking|fix|additive|deprecated)\]$/);
    if (tag) {
      return '<span class="tag tag--' + tag[1] + '">' + tag[1] + '</span>';
    }
    return '<code>' + escapeHtml(raw) + '</code>';
  });
  return out;
}

/** Render a contiguous bullet-list block (up to two indent levels). */
function renderList(blockLines) {
  const items = [];
  for (const ln of blockLines) {
    const m = ln.match(/^(\s*)-\s+([\s\S]*)$/);
    if (m) {
      items.push({ level: m[1].length >= 2 ? 1 : 0, text: [m[2]] });
    } else if (items.length) {
      items[items.length - 1].text.push(ln.trim());
    }
  }
  let html = '<ul>';
  let subOpen = false;
  let liOpen = false;
  for (const it of items) {
    const content = renderInline(it.text.join(' '));
    if (it.level === 0) {
      if (subOpen) {
        html += '</ul>';
        subOpen = false;
      }
      if (liOpen) {
        html += '</li>';
      }
      html += '<li>' + content;
      liOpen = true;
    } else {
      if (!subOpen) {
        html += '<ul>';
        subOpen = true;
      }
      html += '<li>' + content + '</li>';
    }
  }
  if (subOpen) html += '</ul>';
  if (liOpen) html += '</li>';
  html += '</ul>';
  return html;
}

/** Parse the Markdown into ordered blocks. */
function parseBlocks(md) {
  const lines = md.replace(/\r\n/g, '\n').replace(/\s+$/, '').split('\n');
  const blocks = [];
  let para = [];
  const flushPara = () => {
    if (para.length) {
      blocks.push({ tag: 'p', html: '<p>' + renderInline(para.join(' ')) + '</p>', text: para.join(' ') });
      para = [];
    }
  };
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (/^\s*$/.test(line)) {
      flushPara();
      i++;
      continue;
    }
    const heading = line.match(/^(#{1,3})\s+(.*)$/);
    if (heading) {
      flushPara();
      const level = heading[1].length;
      blocks.push({
        tag: 'h' + level,
        html: '<h' + level + '>' + renderInline(heading[2]) + '</h' + level + '>',
        text: heading[2],
      });
      i++;
      continue;
    }
    if (/^---+\s*$/.test(line)) {
      flushPara();
      blocks.push({ tag: 'hr', html: '', text: '' });
      i++;
      continue;
    }
    if (/^\s*-\s+/.test(line)) {
      flushPara();
      const blockLines = [];
      while (i < lines.length && !/^\s*$/.test(lines[i])) {
        if (/^#{1,3}\s/.test(lines[i]) || /^---+\s*$/.test(lines[i])) break;
        blockLines.push(lines[i]);
        i++;
      }
      const text = blockLines.join(' ');
      blocks.push({ tag: 'ul', html: renderList(blockLines), text });
      continue;
    }
    para.push(line.trim());
    i++;
  }
  flushPara();
  return blocks;
}

function slug(title) {
  return 'v-' + title.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
}

/** Group blocks into an intro section plus one section per `##` version. */
function buildSections(blocks) {
  const sections = [];
  let current = { id: 'overview', title: 'Overview', navLabel: 'Overview', pieces: [], text: [] };
  for (const b of blocks) {
    if (b.tag === 'hr') continue;
    if (b.tag === 'h2') {
      sections.push(current);
      current = {
        id: slug(b.text),
        title: b.text,
        navLabel: b.text,
        pieces: [b.html],
        text: [b.text],
      };
      continue;
    }
    current.pieces.push(b.html);
    current.text.push(b.text);
  }
  sections.push(current);
  return sections;
}

function renderSectionsHtml(sections) {
  return sections
    .map((s) => {
      const search = s.text.join(' ').toLowerCase().replace(/"/g, '&quot;');
      return (
        '<section class="ver" id="' +
        s.id +
        '" data-search="' +
        search +
        '">\n' +
        s.pieces.join('\n') +
        '\n</section>'
      );
    })
    .join('\n');
}

function renderNavHtml(sections) {
  return sections
    .map(
      (s) =>
        '<a class="navlink" href="#' +
        s.id +
        '" data-target="' +
        s.id +
        '">' +
        renderInline(s.navLabel) +
        '</a>',
    )
    .join('\n');
}

const THEME_INIT =
  '(function(){try{var u=new URLSearchParams(location.search).get("theme");' +
  'var s=u||localStorage.getItem("theme");var t=(s==="light"||s==="dark")?s:"light";' +
  'document.documentElement.setAttribute("data-theme",t);' +
  'if(u==="light"||u==="dark"){try{localStorage.setItem("theme",u);}catch(e){}}}catch(e){}})();';

const PAGE_SCRIPT = [
  "var tb=document.getElementById('themeBtn');",
  'if(tb)tb.addEventListener(\'click\',function(){',
  "  var cur=document.documentElement.getAttribute('data-theme')==='light'?'dark':'light';",
  "  document.documentElement.setAttribute('data-theme',cur);",
  "  try{localStorage.setItem('theme',cur);}catch(e){}",
  '});',
  "var filter=document.getElementById('filter');",
  "var sections=Array.prototype.slice.call(document.querySelectorAll('section.ver'));",
  "var navlinks=Array.prototype.slice.call(document.querySelectorAll('a.navlink'));",
  'if(filter)filter.addEventListener(\'input\',function(){',
  '  var q=filter.value.trim().toLowerCase();',
  '  sections.forEach(function(sec){',
  "    var hit=!q||(sec.getAttribute('data-search')||'').indexOf(q)!==-1;",
  "    sec.style.display=hit?'':'none';",
  '  });',
  '  navlinks.forEach(function(a){',
  "    var id=a.getAttribute('data-target');",
  "    var sec=document.getElementById(id);",
  "    a.style.display=(sec&&sec.style.display!=='none')?'':'none';",
  '  });',
  '});',
].join('\n');

export function buildChangelogHtml(markdown) {
  const blocks = parseBlocks(markdown);
  const sections = buildSections(blocks);
  const navHtml = renderNavHtml(sections);
  const bodyHtml = renderSectionsHtml(sections);

  return `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>peek-app-utilities — Changelog</title>
<script>${THEME_INIT}</script>
<style>
  :root{
    --bg:#0d1117; --panel:#161b22; --panel2:#1c2330; --border:#2a3441;
    --text:#e6edf3; --muted:#8b949e; --accent:#58a6ff; --accent2:#3fb950;
    --mono:ui-monospace,SFMono-Regular,"SF Mono",Menlo,Consolas,monospace;
    --red:#f85149; --amber:#d29922;
  }
  html[data-theme="light"]{
    --bg:#f6f8fa; --panel:#ffffff; --panel2:#eef1f5; --border:#d0d7de;
    --text:#1f2328; --muted:#59636e; --accent:#0969da; --accent2:#1a7f37;
    --red:#cf222e; --amber:#9a6700;
  }
  *{box-sizing:border-box}
  html,body{margin:0;min-height:100%}
  body{background:var(--bg);color:var(--text);font:15px/1.65 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}
  a{color:var(--accent);text-decoration:none}
  a:hover{text-decoration:underline}
  code{font-family:var(--mono);font-size:.88em;background:var(--panel2);border:1px solid var(--border);border-radius:5px;padding:1px 5px}
  .themebtn{position:fixed;top:16px;right:18px;background:var(--panel2);border:1px solid var(--border);color:var(--text);border-radius:6px;padding:4px 11px;cursor:pointer;font-size:15px;z-index:20}
  .themebtn:hover{border-color:var(--accent);color:var(--accent)}
  .layout{display:grid;grid-template-columns:260px minmax(0,860px);gap:40px;max-width:1180px;margin:0 auto;padding:0 20px 90px}
  nav.side{position:sticky;top:0;align-self:start;height:100vh;overflow-y:auto;padding:30px 0 30px;display:flex;flex-direction:column}
  nav.side .brand{font-weight:700;font-size:15px;margin:0 0 2px}
  nav.side .brand .kind{display:block;font-family:var(--mono);font-size:11px;color:var(--muted);font-weight:400;margin-top:3px}
  nav.side .filterwrap{margin:16px 0 10px}
  nav.side input#filter{width:100%;background:var(--panel);border:1px solid var(--border);color:var(--text);border-radius:7px;padding:7px 10px;font-size:13px;font-family:inherit}
  nav.side input#filter:focus{outline:none;border-color:var(--accent)}
  nav.side .navlabel{font-size:11px;text-transform:uppercase;letter-spacing:.8px;color:var(--muted);margin:10px 0 6px}
  nav.side a.navlink{display:block;color:var(--muted);font-size:13.5px;padding:4px 10px;border-radius:6px;border-left:2px solid transparent}
  nav.side a.navlink:hover{color:var(--text);background:var(--panel);text-decoration:none}
  nav.side a.navlink.active{color:var(--accent);border-left-color:var(--accent);background:var(--panel)}
  main{min-width:0;padding-top:30px}
  main h1{font-size:30px;letter-spacing:.2px;margin:0 0 6px}
  main h2{font-size:21px;margin:0 0 4px;padding-bottom:8px;border-bottom:1px solid var(--border)}
  main h3{font-size:16px;margin:22px 0 2px;line-height:1.45}
  main p{color:var(--text)}
  main section.ver{scroll-margin-top:20px;margin-bottom:40px}
  main section#overview{margin-bottom:30px}
  main section#overview p{color:var(--muted)}
  main ul{margin:8px 0 14px;padding-left:22px}
  main li{margin:4px 0}
  main li ul{margin:5px 0 6px}
  .tag{display:inline-block;font-family:var(--mono);font-size:11px;font-weight:600;padding:1px 8px;border-radius:999px;vertical-align:middle;border:1px solid transparent}
  .tag--additive{color:var(--accent2);border-color:var(--accent2);background:color-mix(in srgb,var(--accent2) 12%,transparent)}
  .tag--fix{color:var(--accent);border-color:var(--accent);background:color-mix(in srgb,var(--accent) 12%,transparent)}
  .tag--breaking{color:var(--red);border-color:var(--red);background:color-mix(in srgb,var(--red) 12%,transparent)}
  .tag--deprecated{color:var(--amber);border-color:var(--amber);background:color-mix(in srgb,var(--amber) 12%,transparent)}
  @media (max-width:840px){
    .layout{grid-template-columns:1fr;gap:0}
    nav.side{position:static;height:auto;overflow:visible;padding:24px 0 0}
    nav.side a.navlink{display:inline-block}
  }
</style>
</head>
<body>
<button id="themeBtn" class="themebtn" title="Toggle light/dark" aria-label="Toggle theme">◐</button>
<div class="layout">
<nav class="side">
  <div class="brand">Changelog<span class="kind">peek-app-utilities</span></div>
  <div class="filterwrap"><input id="filter" type="search" placeholder="Filter versions…" aria-label="Filter changelog" /></div>
  <div class="navlabel">Versions</div>
${navHtml}
  <div class="navlabel" style="margin-top:auto">Reference</div>
  <a class="navlink" href="../index.html">← All docs</a>
</nav>
<main>
${bodyHtml}
</main>
</div>
<script>
${PAGE_SCRIPT}
</script>
</body>
</html>
`;
}

function main() {
  const md = readFileSync(CHANGELOG_MD, 'utf8');
  const html = buildChangelogHtml(md);
  const check = process.argv.includes('--check');
  if (check) {
    let current = '';
    try {
      current = readFileSync(CHANGELOG_HTML, 'utf8');
    } catch {
      current = '';
    }
    if (current !== html) {
      console.error(
        'docs/html/changelog.html is out of date with changelog.md.\n' +
          'Run: node scripts/build-changelog-html.mjs',
      );
      process.exitCode = 1;
      return;
    }
    console.log('docs/html/changelog.html is up to date.');
    return;
  }
  writeFileSync(CHANGELOG_HTML, html);
  console.log('Wrote docs/html/changelog.html (' + TAG_KINDS.length + ' tag kinds supported).');
}

// Run the CLI only when invoked directly, not when imported by the drift test.
if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) {
  main();
}
