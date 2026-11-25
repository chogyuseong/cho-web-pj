// First paint from the edge while the container is asleep.
//
// The Worker still sends every request to the container's Durable Object, as before. For the
// pages and files below (GET/HEAD only), the Durable Object answers with EDGE_SIGNAL instead
// of waiting when its container is not running or is still starting up from cold; it starts
// the container in the background. The Worker then answers from the files deployed with it:
// the two HTML pages built by build-edge-pages.mjs and datemate/static as Workers Static
// Assets. Once the container is running, everything goes to the container exactly as before,
// so a container still running an older image after a deploy never gets mixed with the
// newer HTML or JavaScript deployed with the Worker.

import {
  validPublicOrigin, validDatabaseUrl, internalProbePath, edgeRateLimitKey, staticAssetPath,
} from "./validation.mjs";

// Response header the Durable Object uses to say "serve this one from the edge". The
// container's own responses never carry it, and the Worker only reads it for edge routes.
export const EDGE_SIGNAL = "x-datemate-edge";

// The pages the container serves from static HTML without per-request data.
// Raw pathname, like the Worker's other checks; "/%73hared" simply goes to the container.
const EDGE_PAGES = new Set(["/", "/shared"]);

export function edgeRoute(method, pathname) {
  if (method !== "GET" && method !== "HEAD") return null;
  if (EDGE_PAGES.has(pathname)) return { kind: "page", path: pathname };
  if (staticAssetPath(pathname)) return { kind: "static" };
  return null;
}

// Copies of what datemate/app/web_security.py headers() sets in production over HTTPS.
// The policy has no per-request part (no nonce). datemate/tests/test_edge_headers.py
// compares these strings with the Python values, so a change on one side fails the tests.
export const CONTENT_SECURITY_POLICY = "default-src 'self'; script-src 'self' https://oapi.map.naver.com https://*.naver.com https://*.naver.net https://*.navercorp.com https://*.pstatic.net; script-src-attr 'none'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' data: https://fonts.gstatic.com; img-src 'self' data: blob: https:; connect-src 'self' https://www.wikidata.org https://commons.wikimedia.org https://*.naver.com https://*.naver.net https://*.navercorp.com https://*.pstatic.net; media-src 'self'; worker-src 'self' blob:; child-src 'self' blob:; frame-src 'none'; manifest-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'; upgrade-insecure-requests";
export const PERMISSIONS_POLICY = "camera=(), microphone=(), payment=()";
export const STRICT_TRANSPORT_SECURITY = "max-age=31536000";
export const STATIC_CACHE_CONTROL = "public, max-age=0, must-revalidate";
// ?v= equal to the content hash in the pages built with these assets (web_security.py does the same check).
export const STATIC_IMMUTABLE_CACHE_CONTROL = "public, max-age=31536000, immutable";
// datemate/app/user_feedback.py: home_page() drops this link when DATEMATE_FEEDBACK_ENABLED is off.
export const FEEDBACK_NAV_LINK = '<a id="nav-feedback" class="nav-feedback" href="/feedback"><svg class="nav-icon" aria-hidden="true" viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 5h14v10H9l-4 4z"/></svg><span>피드백</span></a>';
export const FEEDBACK_FOOTER_LINK = '<a class="footer-feedback" href="/feedback">의견 보내기</a>';

function requestId() {
  return crypto.randomUUID().replaceAll("-", "");
}

// noStore: pages and error answers (the app's "/", "/shared" and status >= 400 branch).
function securityHeaders(headers, noStore) {
  headers.set("X-Content-Type-Options", "nosniff");
  headers.set("X-Frame-Options", "DENY");
  headers.set("Referrer-Policy", noStore ? "no-referrer" : "strict-origin-when-cross-origin");
  headers.set("X-Request-ID", requestId());
  headers.set("Permissions-Policy", PERMISSIONS_POLICY);
  headers.set("Content-Security-Policy", CONTENT_SECURITY_POLICY);
  headers.set("Strict-Transport-Security", STRICT_TRANSPORT_SECURITY);
  headers.set("Cache-Control", noStore ? "no-store" : STATIC_CACHE_CONTROL);
  return headers;
}

// Same rule as user_feedback.enabled(): only these words switch the feedback tab off.
export function feedbackEnabled(value) {
  const text = String(value ?? "1").trim().toLowerCase();
  return !["0", "false", "off", "no"].includes(text);
}

// robots.txt·sitemap.xml 은 컨테이너를 거치지 않고 Worker 가 늘 직접 답한다(2026-11-19).
// 왜: 컨테이너가 잠들어 있으면 이 두 주소는 깨어날 때까지 기다렸고, 구글 서치 콘솔이 /sitemap.xml 을 '가져올 수 없음'으로 남겼다
//     (사람 브라우저로는 늘 200 이 보여 원인이 가려졌다). 내용은 PUBLIC_ORIGIN 만으로 정해져 컨테이너 상태·배포 버전과 섞일 일이 없다.
// 내용은 datemate/app/search_robots.py 와 글자까지 같아야 한다(DISALLOWED·SITEMAP_PATHS·CACHE). 한쪽을 바꾸면 다른 쪽도 바꾼다.
//   cloudflare/edge.test.mjs 가 이 문자열을, datemate/tests 의 search_robots 테스트가 앱 쪽을 확인한다.
export const CRAWLER_CACHE_CONTROL = "public, max-age=3600";
const ROBOTS_DISALLOWED = ["/api/"];
const SITEMAP_PATHS = ["/"];

function xmlEscape(text) {
  return text.replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;");
}

export function crawlerFile(pathname, origin) {
  if (pathname === "/robots.txt") {
    const lines = ["User-agent: *", ...ROBOTS_DISALLOWED.map((path) => `Disallow: ${path}`), "", `Sitemap: ${origin}/sitemap.xml`];
    return { type: "text/plain; charset=utf-8", body: lines.join("\n") + "\n" };
  }
  if (pathname === "/sitemap.xml") {
    const urls = SITEMAP_PATHS.map((path) => `  <url><loc>${xmlEscape(origin + path)}</loc></url>\n`).join("");
    return {
      type: "application/xml",
      body: '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + urls + "</urlset>\n",
    };
  }
  return null;
}

function crawlerResponse(pathname, method, origin) {
  if (method !== "GET" && method !== "HEAD") return null;
  const file = crawlerFile(pathname, origin);
  if (!file) return null;
  const headers = securityHeaders(new Headers({ "content-type": file.type }), false);
  headers.set("Cache-Control", CRAWLER_CACHE_CONTROL);
  return new Response(method === "HEAD" ? null : file.body, { status: 200, headers });
}

// Same rule as datemate/app/static_pages.py wants_page(): a browser page request (Accept has text/html) outside
// /api/ gets the Korean not-found page; the API and fetch/JSON requests keep the JSON body (2026-11-25 QA-07).
export const NOT_FOUND_PAGE_KEY = "404";
export function wantsPage(pathname, accept) {
  const api = pathname === "/api" || pathname.startsWith("/api/");
  return !api && String(accept ?? "").toLowerCase().includes("text/html");
}

function notFound(request, pages) {
  const html = pages?.[NOT_FOUND_PAGE_KEY];
  const page = typeof html === "string" && wantsPage(new URL(request.url).pathname, request.headers.get("accept"));
  const headers = securityHeaders(new Headers({ "content-type": page ? "text/html; charset=utf-8" : "application/json" }), true);
  const body = page ? html : JSON.stringify({ detail: "Not Found" });
  return new Response(request.method === "HEAD" ? null : body, { status: 404, headers });
}

// Same rule as datemate/app/static_pages.py with_public_origin(): the home page's canonical/og:url/og:image carry
// PUBLIC_ORIGIN_TOKEN, replaced by the PUBLIC_ORIGIN secret (the only source of absolute URLs, like robots.txt).
// Without an origin the tags holding the token are dropped. Python tests compare the two outputs.
export const PUBLIC_ORIGIN_TOKEN = "{{PUBLIC_ORIGIN}}";
const ORIGIN_TAG = /<(?:link|meta)\b[^>]*\{\{PUBLIC_ORIGIN\}\}[^>]*>/g;
function htmlAttribute(text) {
  return text.replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&#x27;");
}
export function withPublicOrigin(html, origin) {
  if (!origin) return html.replace(ORIGIN_TAG, "");
  return html.replaceAll(PUBLIC_ORIGIN_TOKEN, htmlAttribute(origin));
}

export function pageResponse(path, method, env, pages) {
  let html = pages?.[path];
  if (typeof html !== "string") return null;
  html = withPublicOrigin(html, env.PUBLIC_ORIGIN);
  if (path === "/" && !feedbackEnabled(env.DATEMATE_FEEDBACK_ENABLED)) html = html.replace(FEEDBACK_NAV_LINK, "").replace(FEEDBACK_FOOTER_LINK, "");
  const headers = securityHeaders(new Headers({ "content-type": "text/html; charset=utf-8" }), true);
  if (path === "/shared") headers.set("X-Robots-Tag", "noindex, nofollow");
  return new Response(method === "HEAD" ? null : html, { status: 200, headers });
}

// Path inside the assets directory (datemate/static) for a /static/... request, or null when
// the app would not serve a file for it either (empty, "." or ".." segments, bad escapes).
export function assetPathFor(pathname) {
  let path;
  try { path = decodeURIComponent(pathname); } catch { return null; }
  if (!path.startsWith("/static/")) return null;
  const parts = path.slice("/static/".length).split("/");
  if (parts.some((part) => part === "" || part === "." || part === ".." || part.includes("\\"))) return null;
  return "/" + parts.map(encodeURIComponent).join("/");
}

const PASSED_ASSET_HEADERS = ["content-type", "content-length", "etag", "last-modified"];

// "/static/app.js" -> "<12 hex>" for every versioned address in the built pages. The pages and the
// assets come from the same deploy, so a matching ?v= means this file is the one the page asked for.
const versionCache = new WeakMap();
export function assetVersions(pages) {
  if (!pages || typeof pages !== "object") return new Map();
  let versions = versionCache.get(pages);
  if (!versions) {
    versions = new Map();
    for (const html of Object.values(pages)) {
      if (typeof html !== "string") continue;
      for (const [, url, version] of html.matchAll(/(\/static\/[^\s"'<>?]+)\?v=([0-9a-f]{12})/g)) versions.set(url, version);
    }
    versionCache.set(pages, versions);
  }
  return versions;
}

export async function staticResponse(request, env, pages) {
  const url = new URL(request.url);
  const assetPath = assetPathFor(url.pathname);
  if (!assetPath || !env.ASSETS) return notFound(request, pages);
  const forwarded = new Headers();
  for (const name of ["if-none-match", "if-modified-since"]) {
    const value = request.headers.get(name);
    if (value) forwarded.set(name, value);
  }
  const asset = await env.ASSETS.fetch(new Request(new URL(assetPath, "https://assets.local"), {
    method: request.method, headers: forwarded,
  }));
  if (asset.status !== 200 && asset.status !== 304) {
    await asset.body?.cancel();
    return notFound(request, pages);
  }
  const headers = new Headers();
  for (const name of PASSED_ASSET_HEADERS) {
    const value = asset.headers.get(name);
    if (value) headers.set(name, value);
  }
  // The app answers module scripts as text/javascript; keep the same type for .js/.mjs.
  if (/\.m?js$/.test(assetPath)) headers.set("content-type", "text/javascript; charset=utf-8");
  securityHeaders(headers, false);
  const version = url.searchParams.get("v");
  if (version && (asset.status === 200 || asset.status === 304) && assetVersions(pages).get(url.pathname) === version) {
    headers.set("Cache-Control", STATIC_IMMUTABLE_CACHE_CONTROL);
  }
  const body = request.method === "HEAD" || asset.status === 304 ? null : asset.body;
  if (!body) await asset.body?.cancel();
  return new Response(body, { status: asset.status, headers });
}

export function edgeResponse(route, request, env, pages) {
  if (route.kind === "page") return pageResponse(route.path, request.method, env, pages) ?? notFound(request, pages);
  return staticResponse(request, env, pages);
}

// Front shield in front of the app's own limits (240/min per IP range, static excluded).
// Limits live in wrangler.jsonc ("ratelimits"); both windows are 60 seconds.
const RATE_LIMIT_RETRY_SECONDS = "60";

async function withinEdgeLimit(request, env, pathname) {
  const limiter = staticAssetPath(pathname) ? env.EDGE_LIMIT_STATIC : env.EDGE_LIMIT_APP;
  const key = edgeRateLimitKey(request.headers.get("cf-connecting-ip"));
  // Availability first: without a binding (local dev), a key, or a working limiter,
  // let the request through. The app still enforces its own limits behind this.
  if (!limiter || !key) return true;
  try {
    const { success } = await limiter.limit({ key });
    return success !== false;
  } catch {
    return true;
  }
}

// The Worker's fetch handler. `container` is the Durable Object stub; `pages` the built HTML.
export async function handleFetch(request, env, container, pages) {
  if (!validPublicOrigin(env.PUBLIC_ORIGIN) || !validDatabaseUrl(env.DATABASE_URL)) {
    return new Response("Cloudflare deployment requires HTTPS PUBLIC_ORIGIN and TLS PostgreSQL DATABASE_URL", { status: 503 });
  }
  const url = new URL(request.url);
  if (url.origin !== env.PUBLIC_ORIGIN) {
    return new Response("Unknown host", { status: 421 });
  }
  if (internalProbePath(url.pathname)) {
    return new Response("Not found", { status: 404 });
  }
  if (!(await withinEdgeLimit(request, env, url.pathname))) {
    // Same body shape as the app's own 429 so the frontend shows the message.
    return new Response(JSON.stringify({ detail: "요청이 많아요. 잠시 후 다시 시도해 주세요." }), {
      status: 429,
      headers: {
        "content-type": "application/json",
        "retry-after": RATE_LIMIT_RETRY_SECONDS,
        "cache-control": "no-store",
      },
    });
  }
  // 검색 엔진용 두 파일은 컨테이너를 깨우지 않고 여기서 답한다(위 crawlerFile 설명).
  const crawler = crawlerResponse(url.pathname, request.method, env.PUBLIC_ORIGIN);
  if (crawler) return crawler;
  const response = await container().fetch(request);
  const route = edgeRoute(request.method, url.pathname);
  if (!route || response.headers.get(EDGE_SIGNAL) !== "serve") return response;
  await response.body?.cancel();
  return edgeResponse(route, request, env, pages);
}

// Durable Object side: answer from the edge only while there is no running container, or
// while the container this object started from cold is not ready yet. A container that was
// already running (possibly an older image right after a deploy) keeps serving its own pages.
export function serveAtEdge(method, pathname, { running, coldStarting }) {
  return !!edgeRoute(method, pathname) && (!running || !!coldStarting);
}

export function edgeSignal() {
  return new Response(null, { status: 204, headers: { [EDGE_SIGNAL]: "serve", "cache-control": "no-store" } });
}
