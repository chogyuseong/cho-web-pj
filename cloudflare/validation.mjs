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

// The app serves /static/ without its per-IP limits; the Worker counts those requests
// in a separate, larger bucket so one page load does not use up the page/API budget.
// Decoding matches the app's routing (it decodes before matching the /static mount).
export function staticAssetPath(pathname) {
  let path = pathname;
  try { path = decodeURIComponent(pathname); } catch { return false; }
  return path.startsWith("/static/");
}

function ipv4Octets(value) {
  const match = /^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$/.exec(value);
  if (!match) return null;
  const octets = match.slice(1).map(Number);
  return octets.every((octet) => octet <= 255) ? octets : null;
}

function ipv6Hextets(value) {
  let text = value;
  const tail = [];
  if (text.includes(".")) {
    const cut = text.lastIndexOf(":");
    const octets = ipv4Octets(text.slice(cut + 1));
    if (cut < 0 || !octets) return null;
    tail.push((octets[0] << 8) | octets[1], (octets[2] << 8) | octets[3]);
    // Keep "::" intact when the IPv4 part directly follows it (e.g. "::ffff:1.2.3.4" -> "::ffff").
    text = text.slice(0, cut) + (text.slice(cut - 1, cut + 1) === "::" ? ":" : "");
  }
  const halves = text.split("::");
  if (halves.length > 2) return null;
  const parse = (part) => (part === "" ? [] : part.split(":"));
  const head = parse(halves[0]);
  const rest = halves.length === 2 ? parse(halves[1]) : [];
  if (![...head, ...rest].every((group) => /^[0-9a-fA-F]{1,4}$/.test(group))) return null;
  const known = head.length + rest.length + tail.length;
  if (halves.length === 2 ? known > 7 : known !== 8) return null;
  const zeros = Array(8 - known).fill(0);
  return [...head.map((g) => parseInt(g, 16)), ...zeros, ...rest.map((g) => parseInt(g, 16)), ...tail];
}

// Rate-limit key for the Worker, matching the app's range_of(): IPv4 per address,
// IPv6 grouped by /64 (one subscriber's prefix, so rotating addresses inside it does not
// reset the budget), IPv4-mapped IPv6 treated as the IPv4 address. Returns null when the
// header is missing or not an IP; the caller then skips the edge limit (the app still limits).
export function edgeRateLimitKey(address) {
  const text = String(address ?? "").trim().split("%", 1)[0];
  if (!text) return null;
  const v4 = ipv4Octets(text);
  if (v4) return "ip4:" + v4.join(".");
  if (!text.includes(":")) return null;
  const groups = ipv6Hextets(text);
  if (!groups) return null;
  if (groups.slice(0, 5).every((g) => g === 0) && groups[5] === 0xffff) {
    return "ip4:" + [groups[6] >> 8, groups[6] & 255, groups[7] >> 8, groups[7] & 255].join(".");
  }
  return "ip6:" + groups.slice(0, 4).map((g) => g.toString(16)).join(":") + "::/64";
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
