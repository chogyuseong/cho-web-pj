import { DurableObject } from "cloudflare:workers";

const PORT = 8080;
const IDLE_MS = 10 * 60 * 1000;
const OPTIONAL_ENV = [
  "GMS_KEY", "GMS_BASE_URL", "GMS_MODEL", "EMBEDDING_MODE", "EMBEDDING_MODEL",
  "NAVER_SEARCH_CLIENT_ID", "NAVER_SEARCH_CLIENT_SECRET", "NAVER_MAPS_KEY_ID",
  "NAVER_MAPS_KEY", "NAVER_MAPS_JS_KEY_ID", "TMAP_APP_KEY", "TMAP_TRANSIT_APP_KEY",
  "MAP_TILE_URL", "MAP_TILE_ATTRIBUTION", "WIKI_CONTACT", "PHOTO_VISUAL_CHECK",
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
      if (!this.env.DATABASE_URL || !this.env.PUBLIC_ORIGIN) {
        throw new Error("Set DATABASE_URL and PUBLIC_ORIGIN with wrangler secret put before deployment");
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

export default {
  fetch(request, env) {
    if (!env.PUBLIC_ORIGIN || !env.DATABASE_URL) {
      return new Response("Cloudflare deployment is missing PUBLIC_ORIGIN or DATABASE_URL", { status: 503 });
    }
    let expected;
    try { expected = new URL(env.PUBLIC_ORIGIN).origin; }
    catch { return new Response("Invalid PUBLIC_ORIGIN", { status: 503 }); }
    if (!expected.startsWith("https://") || new URL(request.url).origin !== expected) {
      return new Response("Unknown host", { status: 421 });
    }
    return env.DATEMATE_CONTAINER.getByName("production").fetch(request);
  },
};
