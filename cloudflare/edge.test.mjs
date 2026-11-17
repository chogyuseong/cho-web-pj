import test from "node:test";
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import path from "node:path";
import {
  EDGE_SIGNAL, CONTENT_SECURITY_POLICY, FEEDBACK_NAV_LINK, assetPathFor, edgeRoute, edgeSignal,
  feedbackEnabled, handleFetch, serveAtEdge,
} from "./edge.mjs";
import { DATEMATE_ROOT, buildEdgePages } from "./build-edge-pages.mjs";

const ORIGIN = "https://datemate.example.workers.dev";
const ENV = { PUBLIC_ORIGIN: ORIGIN, DATABASE_URL: "postgresql://u:p@db.example.com/app?sslmode=require" };
const PAGES = buildEdgePages();
const STATIC_DIR = path.join(DATEMATE_ROOT, "static");

// Stand-in for the Workers Static Assets binding: serves datemate/static by path, with ETag.
const ASSETS = {
  calls: [],
  async fetch(request) {
    const url = new URL(request.url);
    this.calls.push(url.pathname);
    let bytes;
    try { bytes = readFileSync(path.join(STATIC_DIR, ...decodeURIComponent(url.pathname).split("/").filter(Boolean))); }
    catch { return new Response(null, { status: 404 }); }
    const etag = '"' + createHash("sha256").update(bytes).digest("hex").slice(0, 16) + '"';
    if (request.headers.get("if-none-match") === etag) return new Response(null, { status: 304, headers: { etag } });
    const type = url.pathname.endsWith(".css") ? "text/css" : url.pathname.endsWith(".js") ? "application/javascript" : "application/octet-stream";
    return new Response(request.method === "HEAD" ? null : bytes, { headers: { "content-type": type, etag, "x-asset-only": "1" } });
  },
};

// Durable Object stub that either signals "edge" (container asleep) or answers as the container.
function container(asleep) {
  const seen = [];
  const stub = {
    seen,
    async fetch(request) {
      seen.push(new URL(request.url).pathname);
      if (asleep && serveAtEdge(request.method, new URL(request.url).pathname, { running: false })) return edgeSignal();
      return new Response("from container", { headers: { "x-from": "container" } });
    },
  };
  return () => stub;
}

const run = (pathname, { asleep = true, method = "GET", env = {}, headers = {} } = {}) => {
  const stub = container(asleep);
  const request = new Request(ORIGIN + pathname, { method, headers });
  return handleFetch(request, { ...ENV, ASSETS, ...env }, stub, PAGES).then((response) => ({ response, seen: stub().seen }));
};

function assertAppHeaders(response, { page }) {
  const h = response.headers;
  assert.equal(h.get("x-content-type-options"), "nosniff");
  assert.equal(h.get("x-frame-options"), "DENY");
  assert.equal(h.get("permissions-policy"), "camera=(), microphone=(), payment=()");
  assert.equal(h.get("content-security-policy"), CONTENT_SECURITY_POLICY);
  assert.equal(h.get("strict-transport-security"), "max-age=31536000");
  assert.match(h.get("x-request-id"), /^[0-9a-f]{32}$/);
  assert.equal(h.get("referrer-policy"), page ? "no-referrer" : "strict-origin-when-cross-origin");
  assert.equal(h.get("cache-control"), page ? "no-store" : "public, max-age=0, must-revalidate");
  assert.equal(h.get("set-cookie"), null);
  assert.equal(h.get(EDGE_SIGNAL), null);
}

test("edge routes: only GET/HEAD of the home page, the shared page and /static/ files", () => {
  assert.deepEqual(edgeRoute("GET", "/"), { kind: "page", path: "/" });
  assert.deepEqual(edgeRoute("HEAD", "/shared"), { kind: "page", path: "/shared" });
  assert.deepEqual(edgeRoute("GET", "/static/app.js"), { kind: "static" });
  assert.deepEqual(edgeRoute("GET", "/%73tatic/app.js"), { kind: "static" });
  for (const [method, pathname] of [
    ["POST", "/"], ["GET", "/api/status"], ["GET", "/feedback"], ["GET", "/feedback/admin"],
    ["GET", "/robots.txt"], ["GET", "/sitemap.xml"], ["GET", "/favicon.ico"], ["GET", "/index.html"],
    ["GET", "/shared/"], ["GET", "/%73hared"], ["DELETE", "/static/app.js"], ["GET", "/readyz"],
  ]) assert.equal(edgeRoute(method, pathname), null, method + " " + pathname);
});

test("the Durable Object hands pages to the edge only while no container is running or a cold start is under way", () => {
  assert.equal(serveAtEdge("GET", "/", { running: false }), true);
  assert.equal(serveAtEdge("GET", "/static/app.js", { running: true, coldStarting: true }), true);
  // Running container (maybe an older image right after a deploy): it keeps serving its own pages.
  assert.equal(serveAtEdge("GET", "/", { running: true, coldStarting: false }), false);
  assert.equal(serveAtEdge("GET", "/api/status", { running: false }), false);
  assert.equal(serveAtEdge("POST", "/", { running: false }), false);
});

test("built pages match versioned_page(): only ?v=<sha256[:12]> added to existing /static js and css", () => {
  for (const [route, name] of [["/", "index.html"], ["/shared", "shared.html"]]) {
    const html = PAGES[route];
    const source = readFileSync(path.join(STATIC_DIR, name), "utf8").replace(/\r\n?/g, "\n");
    assert.equal(html.replace(/\?v=[0-9a-f]{12}/g, ""), source, route);
    const urls = [...html.matchAll(/(\/static\/[^\s"'<>?]+\.(?:js|css))(\?v=([0-9a-f]{12}))?/g)];
    assert.ok(urls.length > 3, route);
    for (const [, url, , version] of urls) {
      const digest = createHash("sha256").update(readFileSync(path.join(DATEMATE_ROOT, ...url.split("/").filter(Boolean)))).digest("hex");
      assert.equal(version, digest.slice(0, 12), url);
    }
  }
  assert.match(PAGES["/"], /<meta name="google-site-verification" content="[^"]+">/);
  assert.ok(PAGES["/"].includes(FEEDBACK_NAV_LINK));
});

test("asleep: the home page comes from the edge with the app's headers and no cookie", async () => {
  const { response, seen } = await run("/?plan=abc");
  assert.equal(response.status, 200);
  assert.equal(response.headers.get("content-type"), "text/html; charset=utf-8");
  assertAppHeaders(response, { page: true });
  assert.equal(response.headers.get("x-robots-tag"), null);
  assert.equal(await response.text(), PAGES["/"]);
  assert.deepEqual(seen, ["/"], "the Durable Object is still asked, which starts the container");
});

test("asleep: the feedback switch removes the header tab like home_page()", async () => {
  assert.equal(feedbackEnabled(undefined), true);
  assert.equal(feedbackEnabled("1"), true);
  for (const value of ["0", " off ", "FALSE", "no", 0]) assert.equal(feedbackEnabled(value), false, String(value));
  const { response } = await run("/", { env: { DATEMATE_FEEDBACK_ENABLED: "0" } });
  const html = await response.text();
  assert.ok(!html.includes(FEEDBACK_NAV_LINK));
  assert.equal(html, PAGES["/"].replace(FEEDBACK_NAV_LINK, ""));
});

test("asleep: the shared page keeps noindex and no-referrer", async () => {
  const { response } = await run("/shared");
  assertAppHeaders(response, { page: true });
  assert.equal(response.headers.get("x-robots-tag"), "noindex, nofollow");
  assert.equal(await response.text(), PAGES["/shared"]);
  const head = (await run("/shared", { method: "HEAD" })).response;
  assert.equal(head.status, 200);
  assert.equal(await head.text(), "");
});

test("asleep: static files come from the deployed assets with the app's static headers", async () => {
  const { response } = await run("/static/app.js?v=whatever");
  assert.equal(response.status, 200);
  assertAppHeaders(response, { page: false });
  assert.equal(response.headers.get("content-type"), "text/javascript; charset=utf-8");
  assert.equal(response.headers.get("x-asset-only"), null);
  assert.equal(await response.text(), readFileSync(path.join(STATIC_DIR, "app.js"), "utf8"));
  const css = (await run("/static/vendor/leaflet/leaflet.css")).response;
  assert.equal(css.headers.get("content-type"), "text/css");
  const etag = css.headers.get("etag");
  assert.ok(etag);
  const again = (await run("/static/vendor/leaflet/leaflet.css", { headers: { "if-none-match": etag } })).response;
  assert.equal(again.status, 304);
  assert.equal(await again.text(), "");
  assertAppHeaders(again, { page: false });
});

test("asleep: missing or escaping static paths answer 404 like the app, never another file", async () => {
  for (const pathname of [
    "/static/nope.js", "/static/..%2F..%2Fwrangler.jsonc", "/static/%2e%2e%2fapp%2fmain.py", "/static/x%2F..%2F..%2Fpackage.json",
    "/static/", "/static//app.js", "/static/a%5C..%5Capp.js",
  ]) {
    const { response } = await run(pathname);
    assert.equal(response.status, 404, pathname);
    assert.deepEqual(await response.json(), { detail: "Not Found" }, pathname);
    assertAppHeaders(response, { page: true });
  }
  assert.equal(assetPathFor("/static/vendor/leaflet/leaflet.js"), "/vendor/leaflet/leaflet.js");
  assert.equal(assetPathFor("/static/app.js%3Fx"), "/app.js%3Fx");
  assert.equal(assetPathFor("/static/%E0%A4%A"), null);
});

test("awake: pages, static files and the API all still come from the container", async () => {
  for (const pathname of ["/", "/shared", "/static/app.js", "/api/status", "/feedback", "/robots.txt"]) {
    const { response, seen } = await run(pathname, { asleep: false });
    assert.equal(await response.text(), "from container", pathname);
    assert.deepEqual(seen, [new URL(ORIGIN + pathname).pathname]);
  }
});

test("asleep: everything else still waits for the container (API, POST, other pages)", async () => {
  for (const [pathname, method] of [["/api/status", "GET"], ["/", "POST"], ["/feedback", "GET"], ["/sitemap.xml", "GET"]]) {
    const { response } = await run(pathname, { method });
    assert.equal(response.headers.get("x-from"), "container", pathname);
  }
});

test("the Worker's front checks still run before the edge answers", async () => {
  const stub = container(true);
  const other = await handleFetch(new Request("https://other.example.com/"), { ...ENV, ASSETS }, stub, PAGES);
  assert.equal(other.status, 421);
  for (const pathname of ["/readyz", "/healthz", "/%72eadyz"]) {
    assert.equal((await run(pathname)).response.status, 404, pathname);
  }
  const limited = [];
  const limiter = (name) => ({ async limit() { limited.push(name); return { success: false }; } });
  const env = { EDGE_LIMIT_APP: limiter("app"), EDGE_LIMIT_STATIC: limiter("static") };
  const headers = { "cf-connecting-ip": "203.0.113.7" };
  const page = (await run("/", { env, headers })).response;
  const file = (await run("/static/app.js", { env, headers })).response;
  assert.equal(page.status, 429);
  assert.equal(file.status, 429);
  assert.deepEqual(limited, ["app", "static"]);
  assert.equal(stub().seen.length, 0);
  const misconfigured = await handleFetch(new Request(ORIGIN + "/"), { PUBLIC_ORIGIN: ORIGIN, ASSETS }, stub, PAGES);
  assert.equal(misconfigured.status, 503);
});

test("a container answer that happens to carry the signal is ignored outside edge routes", async () => {
  const stub = () => ({ async fetch() { return edgeSignal(); } });
  const response = await handleFetch(new Request(ORIGIN + "/api/status"), { ...ENV, ASSETS }, stub, PAGES);
  assert.equal(response.status, 204);
});

test("static files: immutable only when ?v= is the content hash the built pages use", async () => {
  const versioned = PAGES["/"].match(/\/static\/app\.js\?v=([0-9a-f]{12})/);
  assert.ok(versioned, "home page links app.js with ?v=");
  const hit = (await run("/static/app.js?v=" + versioned[1])).response;
  assert.equal(hit.status, 200);
  assert.equal(hit.headers.get("cache-control"), "public, max-age=31536000, immutable");
  // An old or made-up hash, or no hash, keeps the revalidating policy.
  for (const suffix of ["?v=000000000000", "?v=" + versioned[1].slice(0, 11), ""]) {
    const other = (await run("/static/app.js" + suffix)).response;
    assert.equal(other.headers.get("cache-control"), "public, max-age=0, must-revalidate", suffix);
  }
  // Fonts and images are not versioned by the pages, so they always revalidate.
  const font = (await run("/static/fonts/line-heading-800.woff2?v=" + versioned[1])).response;
  assert.equal(font.headers.get("cache-control"), "public, max-age=0, must-revalidate");
});
