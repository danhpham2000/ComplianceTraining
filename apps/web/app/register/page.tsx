"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { FormEvent, Suspense, useEffect, useState } from "react";
import { motion } from "framer-motion";
import { ArrowRight } from "lucide-react";
import { useAuth } from "@/components/auth-provider";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { apiRequest } from "@/lib/api";
import { setPendingVerification } from "@/lib/auth-storage";
import { PendingVerification } from "@/lib/types";

function getHomeRoute(role: string) {
  return role === "EMPLOYEE" ? "/employee" : "/dashboard";
}

function RegisterPageContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { actor, ready } = useAuth();
  const [name, setName] = useState(() => searchParams.get("name") ?? "");
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
      const response = await apiRequest<PendingVerification>("/auth/register", {
        method: "POST",
        body: { name, email, password, role: "EMPLOYEE" },
      });
      setPendingVerification({
        email: response.email,
        verificationCodeHint: response.verification_code_hint,
      });
      router.push(`/verify-email?email=${encodeURIComponent(response.email)}`);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to create account.");
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
        className="w-full max-w-lg"
      >
      <Card className="w-full rounded-[2rem] border border-border/70 bg-white/92">
        <CardHeader className="space-y-3 p-8">
          <CardTitle className="text-[1.85rem] tracking-[-0.04em]">Create account</CardTitle>
          <CardDescription className="text-sm leading-6">
            Create your workspace account. Verification is required before access.
          </CardDescription>
        </CardHeader>
        <CardContent className="p-8 pt-0">
          <form className="space-y-4" onSubmit={handleSubmit}>
            <Input
              type="text"
              autoComplete="name"
              placeholder="Full name"
              value={name}
              onChange={(event) => setName(event.target.value)}
              required
            />
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
              autoComplete="new-password"
              placeholder="Create a password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              required
            />

            <Badge variant="default" className="rounded-full px-3 py-1 text-xs">
              Verified email required
            </Badge>

            {error ? <p className="text-sm text-destructive">{error}</p> : null}
            <Button type="submit" className="w-full" disabled={pending}>
              {pending ? "Creating account..." : "Register"}
              {!pending ? <ArrowRight className="size-4" /> : null}
            </Button>
          </form>

          <p className="mt-6 text-sm text-muted-foreground">
            Already have access?{" "}
            <Link href="/login" className="font-medium text-primary">
              Log in
            </Link>
          </p>
        </CardContent>
      </Card>
      </motion.div>
    </div>
  );
}

export default function RegisterPage() {
  return (
    <Suspense fallback={<div className="min-h-full" />}>
      <RegisterPageContent />
    </Suspense>
  );
}
