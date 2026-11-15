import { NextRequest, NextResponse } from "next/server";

const METHODS_WITH_BODY = new Set(["POST", "PUT", "PATCH", "DELETE"]);

function apiOrigin() {
  const origin = process.env.FORGE_API_ORIGIN || process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";
  if (process.env.NODE_ENV === "production" && !origin.startsWith("https://")) {
    throw new Error("FORGE_API_ORIGIN must use HTTPS in production");
  }
  return origin.replace(/\/$/, "");
}

async function proxy(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  const method = request.method;
  if (METHODS_WITH_BODY.has(method) && request.headers.get("origin") !== request.nextUrl.origin) {
    return NextResponse.json({ detail: "Invalid request origin" }, { status: 403 });
  }
  const { path } = await context.params;
  if (!path.every((segment) => /^[A-Za-z0-9_-]+$/.test(segment))) {
    return NextResponse.json({ detail: "Invalid API path" }, { status: 400 });
  }
  if (path.join("/") === "auth/github/exchange") {
    return NextResponse.json({ detail: "Not found" }, { status: 404 });
  }
  const url = `${apiOrigin()}/api/v1/${path.join("/")}${request.nextUrl.search}`;
  const headers = new Headers();
  const contentType = request.headers.get("content-type");
  const orgId = request.headers.get("x-organization-id");
  const session = request.cookies.get("forge_session")?.value;
  if (contentType) headers.set("Content-Type", contentType);
  if (orgId) headers.set("X-Organization-Id", orgId);
  if (session) headers.set("Cookie", `forge_session=${session}`);

  let upstream: Response;
  try {
    upstream = await fetch(url, {
      method,
      headers,
      body: METHODS_WITH_BODY.has(method) ? await request.arrayBuffer() : undefined,
      redirect: "manual",
      cache: "no-store",
      signal: request.signal,
    });
  } catch {
    return NextResponse.json({ detail: "API service unavailable" }, { status: 503 });
  }
  if (method === "GET" && path.join("/") === "auth/github/login" && upstream.ok) {
    let data: { url: string };
    let authorizationURL: URL;
    try {
      const payload: unknown = await upstream.json();
      if (!payload || typeof payload !== "object" || !("url" in payload) || typeof payload.url !== "string") throw new Error("Invalid login URL");
      data = { url: payload.url };
      authorizationURL = new URL(data.url);
    } catch {
      return NextResponse.json({ detail: "Invalid login response" }, { status: 502 });
    }
    const state = authorizationURL.searchParams.get("state");
    if (authorizationURL.origin !== "https://github.com" || !state || !/^[0-9a-f-]{36}$/.test(state)) {
      return NextResponse.json({ detail: "Invalid login response" }, { status: 502 });
    }
    const response = NextResponse.json(data);
    response.headers.set("Cache-Control", "no-store");
    response.cookies.set("forge_oauth_state", state, {
      httpOnly: true,
      secure: process.env.NODE_ENV === "production",
      sameSite: "lax",
      path: "/",
      maxAge: 600,
    });
    return response;
  }
  const response = new NextResponse(upstream.body, {
    status: upstream.status,
    headers: { "Content-Type": upstream.headers.get("content-type") || "application/json", "Cache-Control": "no-store" },
  });
  if (method === "POST" && path.join("/") === "auth/logout" && upstream.ok) {
    response.cookies.delete("forge_session");
  }
  return response;
}

export { proxy as GET, proxy as POST, proxy as PUT, proxy as PATCH, proxy as DELETE };
