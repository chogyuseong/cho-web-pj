export function validPublicOrigin(value) {
  try {
    const url = new URL(value);
    return url.protocol === "https:" && value === url.origin && !url.username && !url.password;
  } catch { return false; }
}

// Container health endpoints are for the Worker's own readiness check (it calls the
// container port directly), not for the public internet.
export function internalProbePath(pathname) {
  let path = pathname;
  // The app decodes percent-escapes before routing, so "/%72eadyz" must match too.
  try { path = decodeURIComponent(pathname); } catch { return true; }
  return path === "/healthz" || path === "/readyz";
}

export function validDatabaseUrl(value) {
  try {
    const url = new URL(value);
    const modes = url.searchParams.getAll("sslmode");
    return ["postgres:", "postgresql:"].includes(url.protocol)
      && !!url.hostname && modes.length === 1
      && ["require", "verify-ca", "verify-full"].includes(modes[0]);
  } catch { return false; }
}
