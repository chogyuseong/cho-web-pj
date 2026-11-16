import { DurableObject } from "cloudflare:workers";
import { validPublicOrigin, validDatabaseUrl, optionalContainerEnv } from "./validation.mjs";
import { handleFetch, serveAtEdge, edgeSignal } from "./edge.mjs";
// Built by cloudflare/build-edge-pages.mjs (wrangler.jsonc "build"); not committed.
import { EDGE_PAGES } from "./generated/edge-pages.mjs";

const PORT = 8080;
const IDLE_MS = 10 * 60 * 1000;

export class DatemateContainer extends DurableObject {
  starting;
  // True only while a container this object started from cold is not ready yet.
  coldStarting = false;

  constructor(ctx, env) {
    super(ctx, env);
    if (ctx.container?.running) {
      void ctx.blockConcurrencyWhile(() => ctx.container.setInactivityTimeout(IDLE_MS));
    }
  }

  ensureStarted() {
    this.starting ??= this.startAndWait().finally(() => {
      this.starting = undefined;
      this.coldStarting = false;
    });
    return this.starting;
  }

  async fetch(request) {
    // Pages and static files: do not hold the visitor on a blank screen while the container
    // boots. Start it in the background and let the Worker answer from its own copy.
    if (serveAtEdge(request.method, new URL(request.url).pathname, {
      running: this.ctx.container?.running, coldStarting: this.coldStarting,
    })) {
      this.ensureStarted().catch(() => {});
      return edgeSignal();
    }

    await this.ensureStarted();

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
      Object.assign(env, optionalContainerEnv(this.env));
      container.start({ image: container.images.base, instance: "standard-1", enableInternet: true, env });
      this.coldStarting = true;
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
    // 사용자·네이버·관광공사·DB가 모두 아시아에 있다. 위치 힌트는 객체를 처음 만들 때만 적용되므로
    // 이름을 바꿔 아시아에 새로 만든다. 영속 데이터는 PostgreSQL에 있어 객체를 바꿔도 잃는 것이 없다.
    const container = () => env.DATEMATE_CONTAINER.get(env.DATEMATE_CONTAINER.idFromName("production-apac"), { locationHint: "apac" });
    return handleFetch(request, env, container, EDGE_PAGES);
  },
};
