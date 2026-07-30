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

  return <div className="app-loading"><span className="loading-orbit" />Securing workspace</div>;
}

export default function CallbackPage() {
  return (
    <main className="login-callback">
      <Suspense fallback={<div className="app-loading">Loading workspace</div>}>
        <CallbackHandler />
      </Suspense>
    </main>
  );
}
