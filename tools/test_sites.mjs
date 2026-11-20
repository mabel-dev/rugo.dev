// Checks the standalone viewer sites build into complete, self-contained static folders.
//   node --test tools/test_sites.mjs
import test from "node:test";
import assert from "node:assert/strict";
import { mkdtemp, readFile, access, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { buildSites } from "./build_sites.mjs";
import { sites } from "./sites/sites.mjs";

const out = await mkdtemp(path.join(tmpdir(), "rugo-sites-"));
await buildSites(out);
test.after(() => rm(out, { recursive: true, force: true }));

const exists = (p) => access(p).then(() => true, () => false);

for (const site of sites) {
  const dir = path.join(out, site.domain);
  const page = () => readFile(path.join(dir, "index.html"), "utf8");

  test(`${site.domain}: page names the format and canonical URL`, async () => {
    const html = await page();
    assert.match(html, new RegExp(`<title>${site.title.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}</title>`));
    assert.ok(html.includes(`<link rel="canonical" href="https://${site.domain}/" />`));
    assert.ok(html.includes(`<h1>${site.h1}</h1>`));
    assert.ok(html.includes("Your file never leaves your machine."));
  });

  test(`${site.domain}: every local file the page references exists`, async () => {
    const html = await page();
    const refs = [...html.matchAll(/(?:href|src|from) ?= ?"\.?\/?([^":#]+\.(?:css|js|svg|mjs))"/g)].map((m) => m[1]);
    assert.ok(refs.includes("viewer/viewer.css") && refs.includes("favicon.svg"));
    for (const ref of refs) assert.ok(await exists(path.join(dir, ref)), `missing ${ref}`);
  });

  test(`${site.domain}: viewer modules, engine and static files are present`, async () => {
    for (const f of [
      "viewer/viewer.js", "viewer/avro.js", "viewer/orc.js", "viewer/engine.js",
      "wasm/rugo_footer.mjs", "wasm/dist/rugo.mjs", "wasm/dist/rugo.wasm",
      "robots.txt", "sitemap.xml", "CNAME",
    ]) assert.ok(await exists(path.join(dir, f)), `missing ${f}`);
    // The rugo.dev page and its README don't belong on a standalone site.
    assert.equal(await exists(path.join(dir, "viewer/index.html")), false);
    assert.equal(await exists(path.join(dir, "viewer/README.md")), false);
    assert.equal((await readFile(path.join(dir, "CNAME"), "utf8")).trim(), site.domain);
    assert.match(await readFile(path.join(dir, "sitemap.xml"), "utf8"), new RegExp(`https://${site.domain}/`));
  });

  test(`${site.domain}: structured data parses and matches the visible FAQ`, async () => {
    const html = await page();
    const m = /<script type="application\/ld\+json">(.*?)<\/script>/s.exec(html);
    const data = JSON.parse(m[1]);
    const faq = data["@graph"].find((n) => n["@type"] === "FAQPage");
    assert.equal(faq.mainEntity.length, site.faq.length);
    for (const q of site.faq) assert.ok(html.includes(`<summary>${q.q}</summary>`), q.q);
  });
}

test("content is escaped, so copy can't inject markup", async () => {
  const { renderPage } = await import("./build_sites.mjs");
  const html = renderPage({
    ...sites[0],
    h1: "<img src=x onerror=alert(1)>",
    faq: [{ q: "</script><script>alert(1)</script>", a: "a & b" }],
  });
  assert.ok(!html.includes("<img src=x"));
  assert.ok(!html.includes("</script><script>alert"));
  assert.ok(html.includes("a &amp; b"));
});
