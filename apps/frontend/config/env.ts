export const env = {
  NEXT_PUBLIC_API_BASE_URL: process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000",
  NEXT_PUBLIC_EVENT_URL: process.env.NEXT_PUBLIC_EVENT_URL || "ws://localhost:8000",
};

if (process.env.NODE_ENV === "production" && process.env.STRICT_PROD === "true") {
  if (!process.env.NEXT_PUBLIC_API_BASE_URL || process.env.NEXT_PUBLIC_API_BASE_URL.includes("localhost")) {
    throw new Error("NEXT_PUBLIC_API_BASE_URL must be defined and point to a production URL in strict production mode.");
  }
  if (!process.env.NEXT_PUBLIC_EVENT_URL || process.env.NEXT_PUBLIC_EVENT_URL.includes("localhost")) {
    throw new Error("NEXT_PUBLIC_EVENT_URL must be defined and point to a production URL in strict production mode.");
  }
}
