import test from "node:test";
import assert from "node:assert/strict";
import { validPublicOrigin, validDatabaseUrl, internalProbePath } from "./validation.mjs";

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
