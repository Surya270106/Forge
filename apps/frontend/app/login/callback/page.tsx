'use client';

import React, { useEffect, useState, Suspense } from "react";
import { useSearchParams, useRouter } from "next/navigation";

function CallbackHandler() {
  const searchParams = useSearchParams();
  const router = useRouter();

  useEffect(() => {
    const orgId = searchParams.get("org_id");
    const token = searchParams.get("token");

    if (orgId) {
      localStorage.setItem("forge_org_id", orgId);
    }
    if (token) {
      localStorage.setItem("forge_token", token);
    }
    router.push("/");
  }, [searchParams, router]);

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
