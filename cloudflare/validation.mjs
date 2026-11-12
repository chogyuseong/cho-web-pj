export function validPublicOrigin(value) {
  try {
    const url = new URL(value);
    return url.protocol === "https:" && value === url.origin && !url.username && !url.password;
  } catch { return false; }
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
