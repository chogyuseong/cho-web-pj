import test from "node:test";
import assert from "node:assert/strict";
import {
  validPublicOrigin, validDatabaseUrl, internalProbePath, edgeRateLimitKey, staticAssetPath,
  optionalContainerEnv, OPTIONAL_CONTAINER_ENV,
} from "./validation.mjs";

test("edge rate-limit key: IPv4 per address", () => {
  assert.equal(edgeRateLimitKey("203.0.113.7"), "ip4:203.0.113.7");
  assert.equal(edgeRateLimitKey(" 203.0.113.7 "), "ip4:203.0.113.7");
  assert.notEqual(edgeRateLimitKey("203.0.113.7"), edgeRateLimitKey("203.0.113.8"));
});

test("edge rate-limit key: IPv6 grouped by /64", () => {
  const key = "ip6:2001:db8:abcd:12::/64";
  for (const value of [
    "2001:db8:abcd:12::1", "2001:db8:abcd:12:ffff:ffff:ffff:ffff",
    "2001:0DB8:ABCD:0012:0000:0000:0000:0001", "2001:db8:abcd:12:1:2:3.4.5.6",
    "2001:db8:abcd:12::9%eth0",
  ]) assert.equal(edgeRateLimitKey(value), key, value);
  assert.notEqual(edgeRateLimitKey("2001:db8:abcd:13::1"), key);
  assert.equal(edgeRateLimitKey("::1"), "ip6:0:0:0:0::/64");
  assert.equal(edgeRateLimitKey("2001:db8::"), "ip6:2001:db8:0:0::/64");
});

test("edge rate-limit key: IPv4-mapped IPv6 counts as the IPv4 address", () => {
  assert.equal(edgeRateLimitKey("::ffff:203.0.113.7"), "ip4:203.0.113.7");
  assert.equal(edgeRateLimitKey("::ffff:cb00:7107"), "ip4:203.0.113.7");
  assert.equal(edgeRateLimitKey("0:0:0:0:0:ffff:203.0.113.7"), "ip4:203.0.113.7");
});

test("edge rate-limit key: missing or invalid header gives no key", () => {
  for (const value of [
    null, undefined, "", "  ", "unknown", "256.1.1.1", "1.2.3", "1.2.3.4.5",
    "1::2::3", "1:2:3:4:5:6:7:8:9", "1:2:3:4:5:6:7", "12345::1", "g::1", ":::", "::ffff:300.1.1.1",
  ]) assert.equal(edgeRateLimitKey(value), null, String(value));
});

test("static asset paths get their own edge bucket", () => {
  for (const path of ["/static/app.js", "/static/img/a.png", "/%73tatic/app.js"]) {
    assert.equal(staticAssetPath(path), true, path);
  }
  for (const path of ["/", "/static", "/api/static/x", "/staticx/a", "/%E0%A4%A"]) {
    assert.equal(staticAssetPath(path), false, path);
  }
});

test("public origin must be one exact HTTPS origin", () => {
  assert.equal(validPublicOrigin("https://date.example.com"), true);
  for (const value of [
    "http://date.example.com", "https://date.example.com/",
    "https://date.example.com/path", "https://date.example.com?x=1",
    "https://user:pass@date.example.com", "not-a-url",
  ]) assert.equal(validPublicOrigin(value), false, value);
});

test("container health probes are not served publicly", () => {
  for (const path of ["/healthz", "/readyz", "/%72eadyz", "/health%7A"]) {
    assert.equal(internalProbePath(path), true, path);
  }
  for (const path of ["/", "/api/status", "/healthz/", "/readyz/x", "/static/readyz", "/HEALTHZ"]) {
    assert.equal(internalProbePath(path), false, path);
  }
});

test("PostgreSQL connections must require TLS without duplicate sslmode", () => {
  assert.equal(validDatabaseUrl("postgresql://user:pass@db.example.com/app?sslmode=require"), true);
  assert.equal(validDatabaseUrl("postgres://user:pass@db.example.com/app?sslmode=verify-full"), true);
  for (const value of [
    "postgresql://user:pass@db.example.com/app",
    "postgresql://user:pass@db.example.com/app?sslmode=prefer",
    "postgresql://user:pass@db.example.com/app?sslmode=disable",
    "postgresql://user:pass@db.example.com/app?sslmode=require&sslmode=disable",
    "https://db.example.com/app?sslmode=require", "not-a-url",
  ]) assert.equal(validDatabaseUrl(value), false, value);
});

test("optional container env skips missing values and carries the feedback settings", () => {
  assert.deepEqual(optionalContainerEnv({}), {});
  assert.deepEqual(optionalContainerEnv(undefined), {});
  const env = optionalContainerEnv({
    FEEDBACK_ADMIN_KEY: "fake-test-value", DATEMATE_FEEDBACK_ENABLED: 0,
    TOUR_API_KEY: undefined, DATABASE_URL: "postgresql://x", UNLISTED: "y",
  });
  assert.deepEqual(env, { FEEDBACK_ADMIN_KEY: "fake-test-value", DATEMATE_FEEDBACK_ENABLED: "0" });
  assert.ok(Object.values(optionalContainerEnv({ GMS_KEY: undefined, NAVER_MAPS_KEY: null })).length === 0);
  for (const name of ["FEEDBACK_ADMIN_KEY", "DATEMATE_FEEDBACK_ENABLED", "TOUR_API_KEY"]) {
    assert.ok(OPTIONAL_CONTAINER_ENV.includes(name), name);
  }
});

test("feedback paths are neither blocked as probes nor counted as static files", () => {
  for (const path of ["/feedback", "/feedback/admin", "/api/feedback", "/api/feedback/admin/entries"]) {
    assert.equal(internalProbePath(path), false, path);
    assert.equal(staticAssetPath(path), false, path);
  }
});
