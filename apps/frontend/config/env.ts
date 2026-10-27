export const env = {
  NEXT_PUBLIC_API_BASE_URL: process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000",
  NEXT_PUBLIC_EVENT_URL: process.env.NEXT_PUBLIC_EVENT_URL || "ws://localhost:8000",
};

if (process.env.NODE_ENV === "production" && process.env.STRICT_PROD === "true") {
  if (!process.env.NEXT_PUBLIC_API_BASE_URL || !/^https:\/\//.test(process.env.NEXT_PUBLIC_API_BASE_URL)) {
    throw new Error("NEXT_PUBLIC_API_BASE_URL must use HTTPS in strict production mode.");
  }
  if (!process.env.NEXT_PUBLIC_EVENT_URL || !/^wss:\/\//.test(process.env.NEXT_PUBLIC_EVENT_URL)) {
    throw new Error("NEXT_PUBLIC_EVENT_URL must use WSS in strict production mode.");
  }
}
