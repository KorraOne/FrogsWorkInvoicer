/** JWT secret for local dev and production. */

export function jwtSecretBytes(env) {
  const value = (env.JWT_SECRET || "").trim();
  if (!value) {
    throw new Error(
      "JWT_SECRET is not set. Add JWT_SECRET=... to account_api/worker/.dev.vars and restart wrangler dev."
    );
  }
  return new TextEncoder().encode(value);
}
