'use client';

import React, { useEffect, useState, Suspense } from "react";
import { useSearchParams, useRouter } from "next/navigation";

function CallbackHandler() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const token = searchParams.get("token");
    const orgId = searchParams.get("org_id");

    if (token) {
      localStorage.setItem("forge_token", token);
      if (orgId) {
        localStorage.setItem("forge_org_id", orgId);
      }
      router.push("/");
    } else {
      setError("Authentication failed: No token received.");
    }
  }, [searchParams, router]);

  if (error) {
    return <div className="text-red-500">{error}</div>;
  }

  return <div className="text-blue-400 animate-pulse">Authenticating...</div>;
}

export default function CallbackPage() {
  return (
    <div className="flex h-screen w-full items-center justify-center bg-background">
      <Suspense fallback={<div>Loading...</div>}>
        <CallbackHandler />
      </Suspense>
    </div>
  );
}
