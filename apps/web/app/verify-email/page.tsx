"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { FormEvent, Suspense, useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import { ArrowRight, MailCheck } from "lucide-react";
import { useAuth } from "@/components/auth-provider";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { apiRequest } from "@/lib/api";
import { clearPendingVerification, getPendingVerification, setPendingVerification } from "@/lib/auth-storage";
import { AuthSession, PendingVerification } from "@/lib/types";

function getHomeRoute(role: string) {
  return role === "EMPLOYEE" ? "/employee" : "/dashboard";
}

function VerifyEmailPageContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { actor, ready, signIn } = useAuth();
  const pendingVerification = useMemo(() => getPendingVerification(), []);
  const [email, setEmail] = useState(searchParams.get("email") ?? pendingVerification?.email ?? "");
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [resending, setResending] = useState(false);

  useEffect(() => {
    if (!ready || !actor) {
      return;
    }
    router.replace(getHomeRoute(actor.role));
  }, [actor, ready, router]);

  async function handleVerify(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);
    setError(null);

    try {
      const session = await apiRequest<AuthSession>("/auth/verify-email", {
        method: "POST",
        body: { email, code },
      });
      clearPendingVerification();
      signIn(session);
      router.replace(getHomeRoute(session.actor.role));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to verify email.");
    } finally {
      setPending(false);
    }
  }

  async function resendCode() {
    setResending(true);
    setError(null);
    try {
      const response = await apiRequest<PendingVerification>("/auth/resend-verification", {
        method: "POST",
        body: { email },
      });
      setPendingVerification({
        email: response.email,
        verificationCodeHint: response.verification_code_hint,
      });
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to resend code.");
    } finally {
      setResending(false);
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
          <Badge variant="primary" className="w-fit gap-2">
            <MailCheck className="size-3.5" />
            Verify email
          </Badge>
          <CardTitle className="text-3xl tracking-[-0.04em]">Confirm your account</CardTitle>
          <CardDescription className="text-sm leading-6">
            Enter the 6-digit code sent to your inbox.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4 p-8 pt-0">
          <form className="space-y-4" onSubmit={handleVerify}>
            <Input
              type="email"
              autoComplete="email"
              placeholder="name@company.com"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              required
            />
            <Input
              type="text"
              inputMode="numeric"
              pattern="[0-9]{6}"
              maxLength={6}
              placeholder="6-digit code"
              value={code}
              onChange={(event) => setCode(event.target.value)}
              required
            />
            {error ? <p className="text-sm text-destructive">{error}</p> : null}
            <Button type="submit" className="w-full" disabled={pending}>
              {pending ? "Verifying..." : "Verify and continue"}
              {!pending ? <ArrowRight className="size-4" /> : null}
            </Button>
          </form>

          <button
            type="button"
            onClick={() => void resendCode()}
            disabled={resending}
            className="text-sm font-medium text-primary"
          >
            {resending ? "Sending a new code..." : "Resend code"}
          </button>
        </CardContent>
      </Card>
      </motion.div>
    </div>
  );
}

export default function VerifyEmailPage() {
  return (
    <Suspense fallback={<div className="min-h-full" />}>
      <VerifyEmailPageContent />
    </Suspense>
  );
}
