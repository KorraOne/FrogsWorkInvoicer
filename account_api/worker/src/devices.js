const PLATFORMS = new Set(["desktop", "browser", "pwa"]);

async function sha256Hex(value) {
  const data = new TextEncoder().encode(String(value));
  const digest = await crypto.subtle.digest("SHA-256", data);
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

/**
 * Upsert a device sighting for an account.
 * Body: { device_id, platform: desktop|browser|pwa, coarse_ua? }
 * Stores only a hash of device_id — never the raw UUID.
 */
export async function upsertAccountDevice(db, userId, body) {
  const deviceId = String(body.device_id || "").trim();
  if (!deviceId || deviceId.length < 8 || deviceId.length > 128) {
    throw new Error("device_id required");
  }
  const platform = String(body.platform || "").trim().toLowerCase();
  if (!PLATFORMS.has(platform)) {
    throw new Error("platform must be desktop, browser, or pwa");
  }
  const coarseUa = String(body.coarse_ua || "")
    .trim()
    .slice(0, 120);
  const deviceIdHash = await sha256Hex(deviceId);
  const now = new Date().toISOString();

  await db
    .prepare(
      `INSERT INTO account_devices (user_id, device_id_hash, platform, coarse_ua, first_seen_at, last_seen_at)
       VALUES (?, ?, ?, ?, ?, ?)
       ON CONFLICT(user_id, device_id_hash) DO UPDATE SET
         platform = excluded.platform,
         coarse_ua = COALESCE(NULLIF(excluded.coarse_ua, ''), account_devices.coarse_ua),
         last_seen_at = excluded.last_seen_at`
    )
    .bind(userId, deviceIdHash, platform, coarseUa || null, now, now)
    .run();
}
