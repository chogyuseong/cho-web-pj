import test from "node:test";
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import path from "node:path";
import {
  EDGE_SIGNAL, CONTENT_SECURITY_POLICY, FEEDBACK_NAV_LINK, FEEDBACK_FOOTER_LINK, assetPathFor, edgeRoute, edgeSignal,
  feedbackEnabled, handleFetch, serveAtEdge, CRAWLER_CACHE_CONTROL, NOT_FOUND_PAGE_KEY, PUBLIC_ORIGIN_TOKEN, wantsPage,
  withPublicOrigin,
} from "./edge.mjs";
import { DATEMATE_ROOT, buildEdgePages, bundledPage, writeBundles } from "./build-edge-pages.mjs";

const ORIGIN = "https://datemate.example.workers.dev";
const ENV = { PUBLIC_ORIGIN: ORIGIN, DATABASE_URL: "postgresql://u:p@db.example.com/app?sslmode=require" };
// 배포(wrangler build)처럼 JS 묶음(static/bundles/, 저장소에 없음)을 먼저 만들고 페이지를 만든다 — CI 의 깨끗한 checkout 에서도 같게.
writeBundles();
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
    // JS 묶기(QA-14, 2026-11-27): 이어진 defer 스크립트 태그들은 묶음 태그 하나로 바뀌고(bundledPage), 그 밖에는 ?v= 만 붙는다.
    const bundled = bundledPage(name, source);
    assert.ok(bundled.includes(`<script src="/static/bundles/${name.replace(".html", ".js")}" defer></script>`), route);
    assert.equal(html.replace(/\?v=[0-9a-f]{12}/g, ""), bundled, route);
    const urls = [...html.matchAll(/(\/static\/[^\s"'<>?]+\.(?:js|css))(\?v=([0-9a-f]{12}))?/g)];
    assert.ok(urls.length > 3, route);
    for (const [, url, , version] of urls) {
      const digest = createHash("sha256").update(readFileSync(path.join(DATEMATE_ROOT, ...url.split("/").filter(Boolean)))).digest("hex");
      assert.equal(version, digest.slice(0, 12), url);
    }
  }
  assert.match(PAGES["/"], /<meta name="google-site-verification" content="[^"]+">/);
  // 네이버 서치어드바이저 소유 확인(2026-11-18). 엣지가 내보내는 첫 화면에도 남아 있어야 한다.
  assert.match(PAGES["/"], /<meta name="naver-site-verification" content="3fb663454990174f24df5e7e69985aab46c3e54b">/);
  assert.ok(PAGES["/"].includes(FEEDBACK_NAV_LINK) && PAGES["/"].includes(FEEDBACK_FOOTER_LINK));
  // The not-found page is built from the same file the app sends (static_pages.NOT_FOUND_PAGE); it is not a route.
  assert.equal(PAGES[NOT_FOUND_PAGE_KEY], readFileSync(path.join(STATIC_DIR, "not-found.html"), "utf8").replace(/\r\n?/g, "\n"));
  assert.equal(edgeRoute("GET", "/404"), null);
});

test("public origin: absolute head tags use PUBLIC_ORIGIN only, and are dropped without one (like with_public_origin)", () => {
  const html = PAGES["/"];
  assert.ok(html.includes(`<link rel="canonical" href="${PUBLIC_ORIGIN_TOKEN}/">`));
  const bare = withPublicOrigin(html, "");
  assert.ok(!bare.includes(PUBLIC_ORIGIN_TOKEN) && !bare.includes('rel="canonical"') && !bare.includes('property="og:url"') && !bare.includes('property="og:image"'));
  assert.ok(bare.includes('<meta name="description"') && bare.includes('property="og:title"'));
  assert.equal(withPublicOrigin(`<link rel="canonical" href="${PUBLIC_ORIGIN_TOKEN}/">`, 'https://a.example/"><x'),
    '<link rel="canonical" href="https://a.example/&quot;&gt;&lt;x/">');
});

test("not-found page only for browser page requests outside /api/", () => {
  assert.equal(wantsPage("/nope", "text/html,application/xhtml+xml"), true);
  assert.equal(wantsPage("/static/nope.js", "TEXT/HTML"), true);
  for (const [pathname, accept] of [["/api/nope", "text/html"], ["/api", "text/html"], ["/nope", "*/*"], ["/nope", "application/json"], ["/nope", null]]) {
    assert.equal(wantsPage(pathname, accept), false, pathname + " " + accept);
  }
});

test("asleep: the home page comes from the edge with the app's headers and no cookie", async () => {
  const { response, seen } = await run("/?plan=abc");
  assert.equal(response.status, 200);
  assert.equal(response.headers.get("content-type"), "text/html; charset=utf-8");
  assertAppHeaders(response, { page: true });
  assert.equal(response.headers.get("x-robots-tag"), null);
  // The canonical/og addresses come from PUBLIC_ORIGIN, as the app does (static_pages.with_public_origin).
  const html = await response.text();
  assert.equal(html, withPublicOrigin(PAGES["/"], ORIGIN));
  assert.ok(html.includes(`<link rel="canonical" href="${ORIGIN}/">`) && html.includes(`<meta property="og:image" content="${ORIGIN}/static/`));
  assert.ok(!html.includes(PUBLIC_ORIGIN_TOKEN) && PAGES["/"].includes(PUBLIC_ORIGIN_TOKEN));
  assert.deepEqual(seen, ["/"], "the Durable Object is still asked, which starts the container");
});

test("asleep: the feedback switch removes the header tab like home_page()", async () => {
  assert.equal(feedbackEnabled(undefined), true);
  assert.equal(feedbackEnabled("1"), true);
  for (const value of ["0", " off ", "FALSE", "no", 0]) assert.equal(feedbackEnabled(value), false, String(value));
  const { response } = await run("/", { env: { DATEMATE_FEEDBACK_ENABLED: "0" } });
  const html = await response.text();
  assert.ok(!html.includes(FEEDBACK_NAV_LINK));
  assert.ok(!html.includes(FEEDBACK_FOOTER_LINK) && !html.includes('href="/feedback"'));
  assert.equal(html, withPublicOrigin(PAGES["/"], ORIGIN).replace(FEEDBACK_NAV_LINK, "").replace(FEEDBACK_FOOTER_LINK, ""));
});

test("asleep: the shared page keeps noindex and no-referrer", async () => {
  const { response } = await run("/shared");
  assertAppHeaders(response, { page: true });
  assert.equal(response.headers.get("x-robots-tag"), "noindex, nofollow");
  // The link preview image address comes from PUBLIC_ORIGIN, as on the home page; there is no canonical/og:url.
  const html = await response.text();
  assert.equal(html, withPublicOrigin(PAGES["/shared"], ORIGIN));
  assert.ok(html.includes(`<meta property="og:image" content="${ORIGIN}/static/images/seoul-evening.jpg">`));
  assert.ok(!html.includes(PUBLIC_ORIGIN_TOKEN) && !html.includes('rel="canonical"') && !html.includes("og:url"));
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
  // A browser page request (Accept: text/html) gets the Korean not-found page, like the app (2026-11-25 QA-07).
  for (const pathname of ["/static/nope.js", "/static/..%2F..%2Fwrangler.jsonc", "/static/"]) {
    const { response } = await run(pathname, { headers: { accept: "text/html,application/xhtml+xml,*/*;q=0.8" } });
    assert.equal(response.status, 404, pathname);
    assert.equal(response.headers.get("content-type"), "text/html; charset=utf-8");
    assertAppHeaders(response, { page: true });
    const html = await response.text();
    assert.equal(html, PAGES[NOT_FOUND_PAGE_KEY]);
    assert.ok(html.includes("찾는 페이지가 없어요") && html.includes(`<a class="home" href="/">`));
  }
  const head = (await run("/static/nope.js", { method: "HEAD", headers: { accept: "text/html" } })).response;
  assert.equal(head.status, 404);
  assert.equal(await head.text(), "");
  assert.equal(assetPathFor("/static/vendor/leaflet/leaflet.js"), "/vendor/leaflet/leaflet.js");
  assert.equal(assetPathFor("/static/app.js%3Fx"), "/app.js%3Fx");
  assert.equal(assetPathFor("/static/%E0%A4%A"), null);
});

test("awake: pages, static files and the API all still come from the container (robots.txt·sitemap.xml are always the Worker's, see below)", async () => {
  for (const pathname of ["/", "/shared", "/static/app.js", "/api/status", "/feedback"]) {
    const { response, seen } = await run(pathname, { asleep: false });
    assert.equal(await response.text(), "from container", pathname);
    assert.deepEqual(seen, [new URL(ORIGIN + pathname).pathname]);
  }
});

test("asleep: everything else still waits for the container (API, POST, other pages)", async () => {
  for (const [pathname, method] of [["/api/status", "GET"], ["/", "POST"], ["/feedback", "GET"], ["/sitemap.xml", "POST"]]) {
    const { response } = await run(pathname, { method });
    assert.equal(response.headers.get("x-from"), "container", pathname);
  }
});

// 구글 서치 콘솔이 '가져올 수 없음'을 남긴 원인(2026-11-19): 잠든 컨테이너를 기다리던 sitemap.xml.
// 내용은 datemate/app/search_robots.py 와 글자까지 같다(아래 기대값은 운영 앱이 실제로 준 본문).
test("robots.txt and sitemap.xml come from the Worker, asleep or awake, without touching the container", async () => {
  for (const asleep of [true, false]) {
    const robots = await run("/robots.txt", { asleep });
    assert.equal(robots.response.status, 200);
    assert.equal(await robots.response.text(), `User-agent: *\nDisallow: /api/\n\nSitemap: ${ORIGIN}/sitemap.xml\n`);
    assert.equal(robots.response.headers.get("content-type"), "text/plain; charset=utf-8");
    const sitemap = await run("/sitemap.xml", { asleep });
    assert.equal(sitemap.response.status, 200);
    assert.equal(await sitemap.response.text(),
      `<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n  <url><loc>${ORIGIN}/</loc></url>\n</urlset>\n`);
    assert.equal(sitemap.response.headers.get("content-type"), "application/xml");
    assert.equal(sitemap.response.headers.get("cache-control"), CRAWLER_CACHE_CONTROL);
    assert.equal(sitemap.response.headers.get("x-content-type-options"), "nosniff");
    assert.deepEqual([...robots.seen, ...sitemap.seen], [], "the container is never asked");
  }
  const head = await run("/sitemap.xml", { method: "HEAD" });
  assert.equal(head.response.status, 200);
  assert.equal(await head.response.text(), "");
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
  // 첫 화면의 JS 는 묶음 하나(2026-11-27 QA-14) — 그 묶음 주소의 ?v= 로 시험한다.
  const versioned = PAGES["/"].match(/\/static\/bundles\/index\.js\?v=([0-9a-f]{12})/);
  assert.ok(versioned, "home page links bundles/index.js with ?v=");
  const hit = (await run("/static/bundles/index.js?v=" + versioned[1])).response;
  assert.equal(hit.status, 200);
  assert.equal(hit.headers.get("cache-control"), "public, max-age=31536000, immutable");
  // An old or made-up hash, or no hash, keeps the revalidating policy.
  for (const suffix of ["?v=000000000000", "?v=" + versioned[1].slice(0, 11), ""]) {
    const other = (await run("/static/bundles/index.js" + suffix)).response;
    assert.equal(other.headers.get("cache-control"), "public, max-age=0, must-revalidate", suffix);
  }
  // QA-19(2026-11-28): 나중에 받는 둘째 묶음(template#later-scripts 안의 주소)도 같은 규칙이다.
  const later = PAGES["/"].match(/<template id="later-scripts">\n<script src="\/static\/bundles\/index-2\.js\?v=([0-9a-f]{12})" defer><\/script>\n<\/template>/);
  assert.ok(later, "home page keeps bundles/index-2.js with ?v= inside template#later-scripts");
  const laterHit = (await run("/static/bundles/index-2.js?v=" + later[1])).response;
  assert.equal(laterHit.status, 200);
  assert.equal(laterHit.headers.get("cache-control"), "public, max-age=31536000, immutable");
  assert.equal((await run("/static/bundles/index-2.js?v=000000000000")).response.headers.get("cache-control"), "public, max-age=0, must-revalidate");
  // Fonts and images are not versioned by the pages, so they always revalidate.
  const font = (await run("/static/fonts/pretendard/Pretendard-Regular.subset.woff2?v=" + versioned[1])).response;
  assert.equal(font.headers.get("cache-control"), "public, max-age=0, must-revalidate");
});
