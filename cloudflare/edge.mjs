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
// datemate/app/user_feedback.py: home_page() drops this link when DATEMATE_FEEDBACK_ENABLED is off.
export const FEEDBACK_NAV_LINK = '<a id="nav-feedback" href="/feedback">피드백</a>';

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

function notFound(method) {
  const headers = securityHeaders(new Headers({ "content-type": "application/json" }), true);
  return new Response(method === "HEAD" ? null : JSON.stringify({ detail: "Not Found" }), { status: 404, headers });
}

export function pageResponse(path, method, env, pages) {
  let html = pages?.[path];
  if (typeof html !== "string") return null;
  if (path === "/" && !feedbackEnabled(env.DATEMATE_FEEDBACK_ENABLED)) html = html.replace(FEEDBACK_NAV_LINK, "");
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

export async function staticResponse(request, env) {
  const assetPath = assetPathFor(new URL(request.url).pathname);
  if (!assetPath || !env.ASSETS) return notFound(request.method);
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
    return notFound(request.method);
  }
  const headers = new Headers();
  for (const name of PASSED_ASSET_HEADERS) {
    const value = asset.headers.get(name);
    if (value) headers.set(name, value);
  }
  // The app answers module scripts as text/javascript; keep the same type for .js/.mjs.
  if (/\.m?js$/.test(assetPath)) headers.set("content-type", "text/javascript; charset=utf-8");
  securityHeaders(headers, false);
  const body = request.method === "HEAD" || asset.status === 304 ? null : asset.body;
  if (!body) await asset.body?.cancel();
  return new Response(body, { status: asset.status, headers });
}

export function edgeResponse(route, request, env, pages) {
  if (route.kind === "page") return pageResponse(route.path, request.method, env, pages) ?? notFound(request.method);
  return staticResponse(request, env);
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
