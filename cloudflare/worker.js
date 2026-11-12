import { DurableObject } from "cloudflare:workers";
import {
  validPublicOrigin, validDatabaseUrl, internalProbePath, edgeRateLimitKey, staticAssetPath,
} from "./validation.mjs";

const PORT = 8080;
const IDLE_MS = 10 * 60 * 1000;
const OPTIONAL_ENV = [
  "GMS_KEY", "GMS_BASE_URL", "GMS_MODEL", "EMBEDDING_MODE", "EMBEDDING_MODEL",
  "NAVER_SEARCH_CLIENT_ID", "NAVER_SEARCH_CLIENT_SECRET", "NAVER_MAPS_KEY_ID",
  "NAVER_MAPS_KEY", "NAVER_MAPS_JS_KEY_ID",
  "MAP_TILE_URL", "MAP_TILE_ATTRIBUTION", "WIKI_CONTACT", "PHOTO_VISUAL_CHECK",
  "TOUR_API_KEY",
];

export class DatemateContainer extends DurableObject {
  starting;

  constructor(ctx, env) {
    super(ctx, env);
    if (ctx.container?.running) {
      void ctx.blockConcurrencyWhile(() => ctx.container.setInactivityTimeout(IDLE_MS));
    }
  }

  async fetch(request) {
    this.starting ??= this.startAndWait().finally(() => { this.starting = undefined; });
    await this.starting;

    const url = new URL(request.url);
    url.protocol = "http:";
    url.host = "container";
    const forwarded = new Request(url, request);
    forwarded.headers.delete("host");
    forwarded.headers.delete("x-forwarded-for");
    forwarded.headers.delete("x-forwarded-proto");
    forwarded.headers.delete("x-forwarded-host");
    forwarded.headers.set("x-forwarded-proto", "https");
    forwarded.headers.set("x-forwarded-for", request.headers.get("cf-connecting-ip") || "unknown");
    return this.ctx.container.getTcpPort(PORT).fetch(forwarded);
  }

  async startAndWait() {
    const container = this.ctx.container;
    if (!container.running) {
      if (!validDatabaseUrl(this.env.DATABASE_URL) || !validPublicOrigin(this.env.PUBLIC_ORIGIN)) {
        throw new Error("Configure a valid HTTPS PUBLIC_ORIGIN and TLS PostgreSQL DATABASE_URL");
      }
      const env = {
        PORT: String(PORT),
        DATEMATE_ENV: "production",
        DATEMATE_RUNTIME: "/data/runtime",
        DATEMATE_BOOTSTRAP_INDEX: "1",
        DATEMATE_DB_POOL_SIZE: "4",
        DATEMATE_PUBLIC_ORIGIN: this.env.PUBLIC_ORIGIN,
        DATEMATE_ALLOWED_HOSTS: "container",
        FORWARDED_ALLOW_IPS: "*",
        DATABASE_URL: this.env.DATABASE_URL,
      };
      for (const key of OPTIONAL_ENV) {
        if (this.env[key] !== undefined) env[key] = this.env[key];
      }
      container.start({ image: container.images.base, instance: "standard-1", enableInternet: true, env });
    }
    await container.setInactivityTimeout(IDLE_MS);
    const port = container.getTcpPort(PORT);
    let error;
    for (let attempt = 0; attempt < 240; attempt++) {
      try {
        const response = await port.fetch("http://container/readyz", { signal: AbortSignal.timeout(2000) });
        await response.body?.cancel();
        if (response.ok) return;
        error = new Error(`Readiness returned ${response.status}`);
      } catch (cause) {
        error = cause;
      }
      await scheduler.wait(500);
    }
    throw new Error("Datemate container did not become ready", { cause: error });
  }
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

export default {
  async fetch(request, env) {
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
    // 사용자·네이버·관광공사·DB가 모두 아시아에 있다. 위치 힌트는 객체를 처음 만들 때만 적용되므로
    // 이름을 바꿔 아시아에 새로 만든다. 영속 데이터는 PostgreSQL에 있어 객체를 바꿔도 잃는 것이 없다.
    const id = env.DATEMATE_CONTAINER.idFromName("production-apac");
    return env.DATEMATE_CONTAINER.get(id, { locationHint: "apac" }).fetch(request);
  },
};
