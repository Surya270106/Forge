import { NextRequest, NextResponse } from "next/server";

function apiOrigin() {
  const origin = process.env.FORGE_API_ORIGIN || process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";
  if (process.env.NODE_ENV === "production" && !origin.startsWith("https://")) {
    throw new Error("FORGE_API_ORIGIN must use HTTPS in production");
  }
  return origin.replace(/\/$/, "");
}

export async function POST(request: NextRequest) {
  if (request.headers.get("origin") !== request.nextUrl.origin) {
    return NextResponse.json({ detail: "Invalid request origin" }, { status: 403 });
  }
  const { code } = await request.json();
  if (typeof code !== "string" || code.length < 16 || code.length > 128) {
    return NextResponse.json({ detail: "Invalid login code" }, { status: 400 });
  }
  let upstream: Response;
  try {
    upstream = await fetch(`${apiOrigin()}/api/v1/auth/github/exchange`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code }),
      cache: "no-store",
    });
  } catch {
    return NextResponse.json({ detail: "Authentication service unavailable" }, { status: 503 });
  }
  if (!upstream.ok) {
    return NextResponse.json({ detail: "Login code expired or already used" }, { status: upstream.status });
  }
  const data: unknown = await upstream.json();
  if (!data || typeof data !== "object" || !("token" in data) || !("org_id" in data)
      || typeof data.token !== "string" || typeof data.org_id !== "string") {
    return NextResponse.json({ detail: "Invalid authentication response" }, { status: 502 });
  }
  const response = NextResponse.json({ org_id: data.org_id });
  response.cookies.set("forge_session", data.token, {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    path: "/",
    maxAge: 7 * 24 * 60 * 60,
  });
  response.headers.set("Cache-Control", "no-store");
  return response;
}
