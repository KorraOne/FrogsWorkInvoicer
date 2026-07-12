const ALLOWED_ORIGINS = new Set([
  "https://app.frogswork.com",
  "https://frogswork.com",
  "https://www.frogswork.com",
  "http://localhost:8090",
  "http://127.0.0.1:8090",
  "http://localhost:8080",
  "http://127.0.0.1:8080",
  "http://localhost:8088",
  "http://127.0.0.1:8088",
]);

export function corsHeaders(request) {
  const origin = request.headers.get("Origin") || "";
  if (!ALLOWED_ORIGINS.has(origin)) {
    return {};
  }
  return {
    "Access-Control-Allow-Origin": origin,
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type, Authorization",
    "Access-Control-Max-Age": "86400",
  };
}

export function withCors(request, response) {
  const headers = new Headers(response.headers);
  for (const [key, value] of Object.entries(corsHeaders(request))) {
    headers.set(key, value);
  }
  return new Response(response.body, {
    status: response.status,
    statusText: response.statusText,
    headers,
  });
}

export function jsonCors(request, data, status = 200) {
  return withCors(
    request,
    new Response(JSON.stringify(data), {
      status,
      headers: { "Content-Type": "application/json" },
    })
  );
}

export function corsPreflight(request) {
  if (request.method !== "OPTIONS") {
    return null;
  }
  return new Response(null, { status: 204, headers: corsHeaders(request) });
}

export function isAllowedOrigin(request) {
  const origin = request.headers.get("Origin") || "";
  return !origin || ALLOWED_ORIGINS.has(origin);
}
