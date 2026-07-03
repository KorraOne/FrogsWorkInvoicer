import { AwsClient } from "aws4fetch";

export const USER_TEST_ORIGIN = "https://frogswork.com";
export const USER_TEST_MAX_BYTES = 400 * 1024 * 1024;
export const USER_TEST_PRESIGN_SEC = 900;
export const USER_TEST_RATE_LIMIT = 5;
export const USER_TEST_RATE_WINDOW_HOURS = 24;

const ANSWER_KEYS = [
  "getting_started",
  "invoice_workflow",
  "confidence_trust",
  "expectations_gaps",
  "overall",
  "pricing_trial",
  "anything_else",
];

export function userTestCorsHeaders(request) {
  const origin = request.headers.get("Origin") || "";
  if (origin !== USER_TEST_ORIGIN) {
    return {};
  }
  return {
    "Access-Control-Allow-Origin": origin,
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
    "Access-Control-Max-Age": "86400",
  };
}

export function withUserTestCors(request, response) {
  const headers = new Headers(response.headers);
  for (const [key, value] of Object.entries(userTestCorsHeaders(request))) {
    headers.set(key, value);
  }
  return new Response(response.body, {
    status: response.status,
    statusText: response.statusText,
    headers,
  });
}

export function jsonUserTest(request, data, status = 200) {
  return withUserTestCors(
    request,
    new Response(JSON.stringify(data), {
      status,
      headers: { "Content-Type": "application/json" },
    })
  );
}

export function errorUserTest(request, message, status) {
  return jsonUserTest(request, { error: message }, status);
}

function bucketName(env) {
  return (env.R2_BUCKET_NAME || "frogswork-invoicer-releases").trim();
}

export async function isUserTestEnabled(db) {
  const row = await db.prepare("SELECT enabled FROM user_test_settings WHERE id = 1").first();
  return Boolean(row?.enabled);
}

export async function setUserTestEnabled(db, enabled) {
  const now = new Date().toISOString();
  await db
    .prepare(
      `INSERT INTO user_test_settings (id, enabled, updated_at) VALUES (1, ?, ?)
       ON CONFLICT(id) DO UPDATE SET enabled = excluded.enabled, updated_at = excluded.updated_at`
    )
    .bind(enabled ? 1 : 0, now)
    .run();
  return enabled;
}

async function hashIp(ip) {
  const data = new TextEncoder().encode(`user-test:${ip || "unknown"}`);
  const buf = await crypto.subtle.digest("SHA-256", data);
  return [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

function clientIp(request) {
  return (
    request.headers.get("CF-Connecting-IP") ||
    request.headers.get("X-Forwarded-For")?.split(",")[0]?.trim() ||
    ""
  );
}

function extensionForType(contentType) {
  const ct = (contentType || "").toLowerCase();
  if (ct.includes("webm")) return "webm";
  if (ct.includes("quicktime") || ct.includes("mov")) return "mov";
  if (ct.includes("mp4") || ct.includes("mpeg")) return "mp4";
  return "bin";
}

function isVideoContentType(contentType) {
  return (contentType || "").toLowerCase().startsWith("video/");
}

function newSubmissionId() {
  return crypto.randomUUID();
}

async function countRecentStarts(db, ipHash) {
  const row = await db
    .prepare(
      `SELECT COUNT(*) AS c FROM user_test_submissions
       WHERE client_ip_hash = ?
         AND datetime(created_at) > datetime('now', ?)`
    )
    .bind(ipHash, `-${USER_TEST_RATE_WINDOW_HOURS} hours`)
    .first();
  return row?.c || 0;
}

function getAwsClient(env) {
  const accessKeyId = env.R2_ACCESS_KEY_ID;
  const secretAccessKey = env.R2_SECRET_ACCESS_KEY;
  if (!accessKeyId || !secretAccessKey) {
    throw new Error("R2 upload is not configured.");
  }
  return new AwsClient({ accessKeyId, secretAccessKey });
}

async function presignedPutUrl(env, key, contentType, contentLength) {
  const accountId = env.R2_ACCOUNT_ID;
  if (!accountId) {
    throw new Error("R2 account is not configured.");
  }
  const bucket = bucketName(env);
  const url = new URL(`https://${accountId}.r2.cloudflarestorage.com/${bucket}/${key}`);
  url.searchParams.set("X-Amz-Expires", String(USER_TEST_PRESIGN_SEC));
  const client = getAwsClient(env);
  const signed = await client.sign(
    new Request(url.toString(), {
      method: "PUT",
      headers: {
        "Content-Type": contentType,
        "Content-Length": String(contentLength),
      },
    }),
    { aws: { signQuery: true } }
  );
  return signed.url;
}

export async function handleUserTestStatus(request, env) {
  if (request.method === "OPTIONS") {
    return withUserTestCors(request, new Response(null, { status: 204 }));
  }
  if (request.method !== "GET") {
    return errorUserTest(request, "Method not allowed", 405);
  }
  const enabled = await isUserTestEnabled(env.DB);
  return jsonUserTest(request, {
    enabled,
    maxBytes: USER_TEST_MAX_BYTES,
    origin: USER_TEST_ORIGIN,
  });
}

export async function handleUserTestCreateSubmission(request, env) {
  if (request.method === "OPTIONS") {
    return withUserTestCors(request, new Response(null, { status: 204 }));
  }
  if (request.method !== "POST") {
    return errorUserTest(request, "Method not allowed", 405);
  }

  let body;
  try {
    body = await request.json();
  } catch {
    body = {};
  }

  if ((body.website || "").trim()) {
    return errorUserTest(request, "Invalid submission.", 400);
  }

  const enabled = await isUserTestEnabled(env.DB);
  if (!enabled) {
    return errorUserTest(request, "Not accepting submissions right now.", 403);
  }

  const ipHash = await hashIp(clientIp(request));
  const recent = await countRecentStarts(env.DB, ipHash);
  if (recent >= USER_TEST_RATE_LIMIT) {
    return errorUserTest(request, "Too many submissions. Try again tomorrow.", 429);
  }

  const contentType = (body.contentType || "").trim();
  const contentLength = Number(body.contentLength || 0);
  const wantsVideo =
    body.hasVideo !== false && isVideoContentType(contentType) && contentLength > 0;

  const id = newSubmissionId();
  const createdAt = new Date().toISOString();

  if (!wantsVideo) {
    await env.DB.prepare(
      `INSERT INTO user_test_submissions
        (id, created_at, video_r2_key, video_bytes, video_content_type, client_ip_hash, status)
       VALUES (?, ?, NULL, NULL, NULL, ?, 'pending_complete')`
    )
      .bind(id, createdAt, ipHash)
      .run();

    return jsonUserTest(request, {
      submissionId: id,
      uploadUrl: null,
      maxBytes: USER_TEST_MAX_BYTES,
    });
  }

  if (!isVideoContentType(contentType)) {
    return errorUserTest(request, "Video file required (video/* content type).", 400);
  }
  if (contentLength < 1 || contentLength > USER_TEST_MAX_BYTES) {
    return errorUserTest(
      request,
      `Video must be between 1 byte and ${USER_TEST_MAX_BYTES} bytes.`,
      400
    );
  }

  const ext = extensionForType(contentType);
  const key = `user-tests/${id}/recording.${ext}`;

  let uploadUrl;
  try {
    uploadUrl = await presignedPutUrl(env, key, contentType, contentLength);
  } catch (exc) {
    return errorUserTest(request, String(exc.message || exc), 503);
  }

  await env.DB.prepare(
    `INSERT INTO user_test_submissions
      (id, created_at, video_r2_key, video_bytes, video_content_type, client_ip_hash, status)
     VALUES (?, ?, ?, ?, ?, ?, 'pending_upload')`
  )
    .bind(id, createdAt, key, contentLength, contentType, ipHash)
    .run();

  return jsonUserTest(request, {
    submissionId: id,
    uploadUrl,
    uploadHeaders: {
      "Content-Type": contentType,
      "Content-Length": String(contentLength),
    },
    maxBytes: USER_TEST_MAX_BYTES,
    expiresIn: USER_TEST_PRESIGN_SEC,
  });
}

export async function handleUserTestComplete(request, env, submissionId) {
  if (request.method === "OPTIONS") {
    return withUserTestCors(request, new Response(null, { status: 204 }));
  }
  if (request.method !== "POST") {
    return errorUserTest(request, "Method not allowed", 405);
  }

  const enabled = await isUserTestEnabled(env.DB);
  if (!enabled) {
    return errorUserTest(request, "Not accepting submissions right now.", 403);
  }

  let body;
  try {
    body = await request.json();
  } catch {
    body = {};
  }

  if ((body.website || "").trim()) {
    return errorUserTest(request, "Invalid submission.", 400);
  }

  const row = await env.DB.prepare("SELECT * FROM user_test_submissions WHERE id = ?")
    .bind(submissionId)
    .first();
  if (!row) {
    return errorUserTest(request, "Submission not found.", 404);
  }
  if (row.status === "complete") {
    return jsonUserTest(request, { ok: true, submissionId });
  }

  const answers = {};
  for (const key of ANSWER_KEYS) {
    const val = (body[key] || "").trim();
    if (!val) {
      return errorUserTest(request, `Missing answer: ${key}`, 400);
    }
    answers[key] = val;
  }

  const testerName = (body.tester_name || "").trim().slice(0, 120) || null;

  let videoBytes = null;
  if (row.video_r2_key) {
    if (!env.RELEASES) {
      return errorUserTest(request, "Storage not configured.", 503);
    }
    const head = await env.RELEASES.head(row.video_r2_key);
    if (!head) {
      return errorUserTest(request, "Video upload not found. Upload the file first.", 400);
    }
    videoBytes = head.size ?? row.video_bytes;
  }

  const completedAt = new Date().toISOString();
  await env.DB.prepare(
    `UPDATE user_test_submissions
     SET completed_at = ?, tester_name = ?, answers_json = ?, video_bytes = ?, status = 'complete'
     WHERE id = ?`
  )
    .bind(completedAt, testerName, JSON.stringify(answers), videoBytes, submissionId)
    .run();

  return jsonUserTest(request, { ok: true, submissionId });
}

export async function listUserTestSubmissions(db, limit = 50) {
  const rows = await db
    .prepare(
      `SELECT id, created_at, completed_at, tester_name, video_bytes, video_content_type, video_r2_key, status
       FROM user_test_submissions
       ORDER BY datetime(created_at) DESC
       LIMIT ?`
    )
    .bind(limit)
    .all();
  const totalBytes = await db
    .prepare(
      `SELECT COALESCE(SUM(video_bytes), 0) AS total FROM user_test_submissions WHERE status = 'complete'`
    )
    .first();
  return {
    submissions: rows.results || [],
    totalVideoBytes: totalBytes?.total || 0,
  };
}

export async function getUserTestSubmission(db, id) {
  return db.prepare("SELECT * FROM user_test_submissions WHERE id = ?").bind(id).first();
}

export async function deleteUserTestSubmission(env, id) {
  const row = await getUserTestSubmission(env.DB, id);
  if (!row) {
    return false;
  }
  if (row.video_r2_key && env.RELEASES) {
    await env.RELEASES.delete(row.video_r2_key);
  }
  await env.DB.prepare("DELETE FROM user_test_submissions WHERE id = ?").bind(id).run();
  return true;
}

export async function getUserTestAdminContext(db) {
  const enabled = await isUserTestEnabled(db);
  const { submissions, totalVideoBytes } = await listUserTestSubmissions(db, 50);
  return { enabled, submissions, totalVideoBytes };
}

export function formatBytes(bytes) {
  if (!bytes) return "—";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export { ANSWER_KEYS };
