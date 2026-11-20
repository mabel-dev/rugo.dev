// Builds the standalone viewer sites (avroviewer.com, orcviewer.com) from docs/viewer and
// docs/wasm into build/sites/<domain>/. Each folder is a complete static site: deploy it as is.
//
//   node tools/build_sites.mjs [outDir]          (default outDir: build/sites)
//
// Hosting: point a static host (Cloudflare Pages, Netlify, S3) at the folder for its domain.
// Build command `node tools/build_sites.mjs`, publish directory `build/sites/<domain>`.

import { cp, mkdir, rm, writeFile, readdir } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import path from "node:path";
import { sites } from "./sites/sites.mjs";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const esc = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
// JSON inside a <script> block must not be able to close it.
const jsonForScript = (o) => JSON.stringify(o).replace(/</g, "\\u003c");

export function renderPage(site) {
  const url = `https://${site.domain}/`;
  const jsonLd = {
    "@context": "https://schema.org",
    "@graph": [
      {
        "@type": "WebApplication",
        name: `${site.format} viewer`,
        url,
        description: site.description,
        applicationCategory: "DeveloperApplication",
        operatingSystem: "Any (runs in the browser)",
        offers: { "@type": "Offer", price: "0", priceCurrency: "USD" },
        isPartOf: { "@type": "WebSite", name: "Rugo Viewer", url },
      },
      {
        "@type": "FAQPage",
        mainEntity: site.faq.map((f) => ({
          "@type": "Question",
          name: f.q,
          acceptedAnswer: { "@type": "Answer", text: f.a },
        })),
      },
    ],
  };
  const cards = site.cards.map((c) => `        <div><h2>${esc(c.h)}</h2><p>${esc(c.p)}</p></div>`).join("\n");
  const faq = site.faq
    .map((f) => `        <details><summary>${esc(f.q)}</summary><p>${esc(f.a)}</p></details>`)
    .join("\n");

  return `<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>${esc(site.title)}</title>
    <meta name="description" content="${esc(site.description)}" />
    <link rel="canonical" href="${url}" />
    <meta property="og:type" content="website" />
    <meta property="og:title" content="${esc(site.title)}" />
    <meta property="og:description" content="${esc(site.description)}" />
    <meta property="og:url" content="${url}" />
    <meta name="twitter:card" content="summary" />
    <link rel="icon" type="image/svg+xml" href="favicon.svg" />
    <link rel="stylesheet" href="viewer/viewer.css" />
    <script type="application/ld+json">${jsonForScript(jsonLd)}</script>
    <style>
      :root { --bg: #0d0f14; --border: #252830; --accent: #4f8ef7; --text: #e2e6f0; --muted: #7a8099; --green: #3ecf8e; --surface: #161920; }
      *, *::before, *::after { box-sizing: border-box; }
      body { margin: 0; background: var(--bg); color: var(--text); font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif; line-height: 1.65; }
      a { color: var(--accent); text-decoration: none; }
      a:hover { text-decoration: underline; }
      nav { position: sticky; top: 0; z-index: 100; background: rgba(13, 15, 20, 0.88); backdrop-filter: blur(12px); border-bottom: 1px solid var(--border); display: flex; align-items: center; justify-content: space-between; gap: 1rem; padding: 0 1rem; height: 56px; }
      .nav-logo { font-weight: 700; font-size: 1.15rem; color: var(--text); }
      .nav-logo span { color: var(--accent); }
      .nav-links { display: flex; gap: 1.25rem; font-size: .92rem; }
      .wrap { max-width: 1000px; margin: 0 auto; padding: 2.5rem 1rem 4rem; }
      h1 { font-size: clamp(1.8rem, 5vw, 2.5rem); line-height: 1.2; margin: 0 0 .6rem; }
      .lead { color: var(--muted); font-size: 1.1rem; max-width: 46rem; margin: 0 0 1.25rem; }
      .private { display: flex; gap: .7rem; align-items: flex-start; border: 1px solid color-mix(in srgb, var(--green) 45%, var(--border)); background: var(--surface); border-radius: 8px; padding: .8rem 1rem; margin: 0 0 1.75rem; }
      .private strong { color: var(--green); }
      .private svg { flex: none; margin-top: .2rem; }
      .how { margin-top: 3rem; display: grid; gap: 1rem; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); }
      .how div { border: 1px solid var(--border); background: var(--surface); border-radius: 8px; padding: 1rem 1.1rem; }
      .how h2 { font-size: 1rem; margin: 0 0 .3rem; }
      .how p { margin: 0; color: var(--muted); font-size: .95rem; }
      .faq { margin-top: 3rem; }
      .faq h2 { font-size: 1.35rem; margin: 0 0 1rem; }
      .faq details { border: 1px solid var(--border); background: var(--surface); border-radius: 8px; padding: .8rem 1.1rem; margin-bottom: .6rem; }
      .faq summary { cursor: pointer; font-weight: 600; }
      .faq details p { margin: .6rem 0 0; color: var(--muted); }
      footer { border-top: 1px solid var(--border); margin-top: 3rem; padding-top: 1.5rem; color: var(--muted); font-size: .9rem; }
      footer p { margin: 0 0 .4rem; }
      noscript { display: block; border: 1px solid var(--border); padding: 1rem; border-radius: 8px; }
      @media (max-width: 640px) { .nav-links a:nth-child(n + 3) { display: none; } }
    </style>
  </head>
  <body>
    <nav>
      <a class="nav-logo" href="/">Rugo <span>Viewer</span></a>
      <div class="nav-links">
        <a href="https://${esc(site.sibling.domain)}/">${esc(site.sibling.label)}</a>
        <a href="https://rugo.dev/viewer/">Parquet viewer</a>
        <a href="https://rugo.dev/">Rugo</a>
        <a href="https://github.com/mabel-dev/opteryx-core/tree/main/rugo">GitHub</a>
      </div>
    </nav>
    <main class="wrap">
      <h1>${esc(site.h1)}</h1>
      <p class="lead">${esc(site.lead)}</p>
      <p class="private">
        <svg width="18" height="18" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true" style="color: var(--green)"><rect x="3" y="7" width="10" height="7" rx="1.5"/><path d="M5.5 7V5a2.5 2.5 0 0 1 5 0v2"/></svg>
        <span><strong>Your file never leaves your machine.</strong> Everything runs in your browser and reads the file straight from your disk. Nothing is uploaded, and there is no server doing the work.</span>
      </p>

      <div id="viewer"></div>
      <noscript>The viewer needs JavaScript and WebAssembly. Both are on by default in current Chrome, Firefox and Safari.</noscript>

      <section class="how" aria-label="What you'll see">
${cards}
      </section>

      <section class="faq" aria-label="Frequently asked questions">
        <h2>Questions</h2>
${faq}
      </section>

      <footer>
        <p>Drop a Parquet, Avro or ORC file and the format is detected from the file itself.</p>
        <p>Built by <a href="https://opteryx.app/">Opteryx</a> on <a href="https://rugo.dev/">Rugo</a>, its open-source data-file reader.</p>
      </footer>
    </main>
    <script type="module">
      import { mountViewer } from "./viewer/viewer.js";
      const url = new URLSearchParams(location.search).get("url");
      mountViewer(document.getElementById("viewer"), { initialUrl: url || undefined });
    </script>
  </body>
</html>
`;
}

async function buildSite(site, outRoot) {
  const out = path.join(outRoot, site.domain);
  await rm(out, { recursive: true, force: true });
  await mkdir(out, { recursive: true });

  // The viewer's modules and styles, minus the rugo.dev page and its README.
  const skip = new Set(["index.html", "README.md"]);
  await cp(path.join(root, "docs/viewer"), path.join(out, "viewer"), {
    recursive: true,
    filter: (src) => !skip.has(path.basename(src)),
  });
  // The WebAssembly engine (Parquet only); Avro and ORC are read in JavaScript.
  await cp(path.join(root, "docs/wasm"), path.join(out, "wasm"), { recursive: true });
  await cp(path.join(root, "docs/favicon.svg"), path.join(out, "favicon.svg"));

  await writeFile(path.join(out, "index.html"), renderPage(site));
  await writeFile(path.join(out, "robots.txt"), `User-agent: *\nAllow: /\n\nSitemap: https://${site.domain}/sitemap.xml\n`);
  await writeFile(
    path.join(out, "sitemap.xml"),
    `<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n  <url><loc>https://${site.domain}/</loc></url>\n</urlset>\n`,
  );
  // Static hosts that read a CNAME file (GitHub Pages) need this; others ignore it.
  await writeFile(path.join(out, "CNAME"), `${site.domain}\n`);
  return out;
}

export async function buildSites(outRoot = path.join(root, "build/sites")) {
  const built = [];
  for (const site of sites) built.push(await buildSite(site, outRoot));
  return built;
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const outRoot = process.argv[2] ? path.resolve(process.argv[2]) : undefined;
  const built = await buildSites(outRoot);
  for (const dir of built) console.log(`built ${path.relative(root, dir)} (${(await readdir(dir)).join(", ")})`);
}
