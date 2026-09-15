"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { FormEvent, Suspense, useEffect, useState } from "react";
import { motion } from "framer-motion";
import { ArrowRight } from "lucide-react";
import { useAuth } from "@/components/auth-provider";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
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
    <div className="flex min-h-full items-center justify-center py-8">
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.45, ease: [0.22, 1, 0.36, 1] }}
        className="w-full max-w-md"
      >
      <Card className="w-full rounded-[2rem] border border-border/70 bg-white/92">
        <CardHeader className="space-y-3 p-8">
          <CardTitle className="text-3xl tracking-[-0.04em]">Log in</CardTitle>
          <CardDescription className="text-sm leading-6">
            Use your verified account to enter the workspace.
          </CardDescription>
        </CardHeader>
        <CardContent className="p-8 pt-0">
          <form className="space-y-4" onSubmit={handleSubmit}>
            <Input
              type="email"
              autoComplete="email"
              placeholder="name@company.com"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              required
            />
            <Input
              type="password"
              autoComplete="current-password"
              placeholder="Password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              required
            />
            {error ? <p className="text-sm text-destructive">{error}</p> : null}
            <Button type="submit" className="w-full" disabled={pending}>
              {pending ? "Signing in..." : "Continue"}
              {!pending ? <ArrowRight className="size-4" /> : null}
            </Button>
          </form>

          <p className="mt-6 text-sm text-muted-foreground">
            Need an account?{" "}
            <Link href="/register" className="font-medium text-primary">
              Register
            </Link>
          </p>
        </CardContent>
      </Card>
      </motion.div>
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
