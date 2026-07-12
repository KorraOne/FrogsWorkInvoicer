const DEFAULT_LIMIT = 10;
const DEFAULT_WINDOW_MS = 15 * 60 * 1000;

export function clientIp(request) {
  return (
    request.headers.get("CF-Connecting-IP") ||
    request.headers.get("X-Forwarded-For")?.split(",")[0]?.trim() ||
    "unknown"
  );
}

export async function checkRateLimit(
  db,
  bucketKey,
  { limit = DEFAULT_LIMIT, windowMs = DEFAULT_WINDOW_MS } = {}
) {
  const now = Date.now();
  const windowStart = new Date(now - windowMs).toISOString();
  const row = await db
    .prepare("SELECT window_start, count FROM rate_limit_buckets WHERE bucket_key = ?")
    .bind(bucketKey)
    .first();

  if (!row || row.window_start < windowStart) {
    await db
      .prepare(
        `INSERT INTO rate_limit_buckets (bucket_key, window_start, count)
         VALUES (?, ?, 1)
         ON CONFLICT(bucket_key) DO UPDATE SET window_start = excluded.window_start, count = 1`
      )
      .bind(bucketKey, new Date(now).toISOString())
      .run();
    return { allowed: true };
  }

  if (row.count >= limit) {
    return { allowed: false, retryAfterSec: Math.ceil(windowMs / 1000) };
  }

  await db
    .prepare("UPDATE rate_limit_buckets SET count = count + 1 WHERE bucket_key = ?")
    .bind(bucketKey)
    .run();
  return { allowed: true };
}

export function rateLimitResponse(retryAfterSec) {
  return new Response(
    JSON.stringify({
      error: "Too many requests. Try again later.",
    }),
    {
      status: 429,
      headers: {
        "Content-Type": "application/json",
        "Retry-After": String(retryAfterSec || 900),
      },
    }
  );
}
