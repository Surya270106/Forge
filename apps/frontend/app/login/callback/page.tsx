'use client';

import React, { useEffect, useState, Suspense } from "react";
import { useSearchParams, useRouter } from "next/navigation";

function CallbackHandler() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const [error, setError] = useState('');

  useEffect(() => {
    const code = searchParams.get('code');
    if (!code) {
      setError('The login link is invalid. Start GitHub sign-in again.');
      return;
    }
    const controller = new AbortController();
    async function exchange() {
      try {
        const response = await fetch(`/api/auth/exchange`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ code }),
          signal: controller.signal,
        });
        if (!response.ok) throw new Error('Sign-in expired. Start GitHub sign-in again.');
        const data = await response.json();
        if (typeof data.org_id !== 'string') {
          throw new Error('Sign-in response was invalid.');
        }
        localStorage.setItem('forge_org_id', data.org_id);
        localStorage.removeItem('forge_token');
        router.replace('/');
      } catch (reason) {
        if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : 'Sign-in failed.');
      }
    }
    void exchange();
    return () => controller.abort();
  }, [searchParams, router]);

  return <div className="app-loading"><span className="loading-orbit" />{error || 'Securing workspace'}</div>;
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
