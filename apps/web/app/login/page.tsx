"use client";

import Image from "next/image";
import { useRouter, useSearchParams } from "next/navigation";
import { FormEvent, Suspense, useEffect, useState } from "react";
import { motion } from "framer-motion";
import { useAuth } from "@/components/auth-provider";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ApiError, apiRequest } from "@/lib/api";
import { setPendingVerification } from "@/lib/auth-storage";
import { AuthSession } from "@/lib/types";

function getHomeRoute(role: string) {
  return role === "EMPLOYEE" ? "/employee" : "/dashboard";
}

function LoginPageContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { actor, ready, signIn } = useAuth();
  const [email, setEmail] = useState(() => searchParams.get("email") ?? "");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  useEffect(() => {
    if (!ready || !actor) {
      return;
    }
    router.replace(getHomeRoute(actor.role));
  }, [actor, ready, router]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);
    setError(null);

    try {
      const session = await apiRequest<AuthSession>("/auth/login", {
        method: "POST",
        body: { email, password },
      });
      signIn(session);
      const next = searchParams.get("next");
      router.replace(next && next.startsWith("/") ? next : getHomeRoute(session.actor.role));
    } catch (cause) {
      if (cause instanceof ApiError && cause.status === 403) {
        const payload = cause.payload as {
          detail?: { email?: string; verification_code_hint?: string | null; message?: string };
        };
        const detail = payload.detail;
        if (detail?.email) {
          setPendingVerification({
            email: detail.email,
            verificationCodeHint: detail.verification_code_hint,
          });
          router.push(`/verify-email?email=${encodeURIComponent(detail.email)}`);
          return;
        }
      }
      setError(cause instanceof Error ? cause.message : "Unable to sign in.");
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="grid min-h-screen bg-white lg:grid-cols-[1.05fr_0.95fr]">
      <section className="relative hidden overflow-hidden bg-[#fff7ef] px-12 py-14 lg:flex lg:flex-col xl:px-[14%]">
        <Image
          src="/nextphase-logo.png"
          alt="NextPhase.ai"
          width={255}
          height={56}
          priority
          className="h-auto w-[220px]"
        />
        <div className="my-auto max-w-xl pb-10">
          <p className="text-xs font-semibold uppercase tracking-[0.17em] text-primary">Compliance training</p>
          <h1 className="mt-7 text-5xl font-semibold leading-[1.13] tracking-[-0.055em] text-foreground xl:text-6xl">
            Build a safer workplace, one decision at a time.
          </h1>
          <p className="mt-6 max-w-lg text-lg leading-8 text-[#6f6b65]">
            Research-led training for the moments where good judgment matters most.
          </p>
        </div>
        <p className="text-sm text-[#897b6c]">NextPhase Compliance</p>
      </section>

      <main className="flex min-h-screen items-center px-6 py-10 sm:px-10 lg:px-[18%]">
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4, ease: [0.22, 1, 0.36, 1] }}
          className="mx-auto w-full max-w-md"
        >
          <Image
            src="/nextphase-logo.png"
            alt="NextPhase.ai"
            width={220}
            height={48}
            priority
            className="mb-14 h-auto w-[190px] lg:hidden"
          />
          <p className="text-xs font-semibold uppercase tracking-[0.17em] text-primary">NextPhase Compliance</p>
          <h2 className="mt-4 text-[2rem] font-semibold tracking-[-0.045em] text-foreground">Welcome back</h2>
          <p className="mt-3 text-base leading-7 text-[#6f6b65]">Sign in to continue to your compliance workspace.</p>

          <form className="mt-9 space-y-5" onSubmit={handleSubmit}>
            <label className="grid gap-2 text-sm font-semibold text-foreground" htmlFor="email">
              Email
              <Input
                id="email"
                type="email"
                autoComplete="email"
                placeholder="name@nextphase.ai"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                required
                className="h-12 rounded-xl bg-white"
              />
            </label>
            <label className="grid gap-2 text-sm font-semibold text-foreground" htmlFor="password">
              Password
              <Input
                id="password"
                type="password"
                autoComplete="current-password"
                placeholder="Enter your password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                required
                className="h-12 rounded-xl bg-white"
              />
            </label>
            {error ? <p className="text-sm text-destructive">{error}</p> : null}
            <Button type="submit" className="mt-2 h-12 w-full rounded-xl text-base" disabled={pending}>
              {pending ? "Signing in..." : "Sign in"}
            </Button>
          </form>

          <p className="mt-7 text-sm leading-6 text-muted-foreground">
            Need access? Contact your administrator for an invite.
          </p>
        </motion.div>
      </main>
    </div>
  );
}

export default function LoginPage() {
  return (
    <Suspense fallback={<div className="min-h-full" />}>
      <LoginPageContent />
    </Suspense>
  );
}
