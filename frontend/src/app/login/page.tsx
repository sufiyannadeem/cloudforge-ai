"use client";

import { FormEvent, useState } from "react";

export default function LoginPage() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const response = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          username,
          password,
          next: new URLSearchParams(window.location.search).get("next") ?? "/dashboard",
        }),
        cache: "no-store",
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error ?? "Login failed");
      window.location.assign(payload.redirectTo ?? "/dashboard");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Login failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="min-h-screen flex items-center justify-center px-4 py-12">
      <section className="w-full max-w-md rounded-2xl border border-white/10 bg-black/20 p-8 shadow-2xl">
        <p className="text-sm font-semibold uppercase tracking-[0.2em] text-cyan-400">CloudForge AI</p>
        <h1 className="mt-3 text-2xl font-semibold">Sign in to your platform</h1>
        <p className="mt-2 text-sm opacity-70">Use the operator credentials configured by your platform administrator.</p>
        <form className="mt-7 space-y-4" onSubmit={submit}>
          <label className="block text-sm">Username
            <input className="mt-1 block w-full rounded-lg border border-white/15 bg-transparent px-3 py-2" autoComplete="username" value={username} onChange={(event) => setUsername(event.target.value)} required />
          </label>
          <label className="block text-sm">Password
            <input className="mt-1 block w-full rounded-lg border border-white/15 bg-transparent px-3 py-2" type="password" autoComplete="current-password" value={password} onChange={(event) => setPassword(event.target.value)} required />
          </label>
          {error ? <p role="alert" className="text-sm text-red-400">{error}</p> : null}
          <button className="w-full rounded-lg bg-cyan-500 px-4 py-2.5 font-semibold text-slate-950 disabled:opacity-50" type="submit" disabled={busy}>
            {busy ? "Signing in…" : "Sign in"}
          </button>
        </form>
      </section>
    </main>
  );
}
