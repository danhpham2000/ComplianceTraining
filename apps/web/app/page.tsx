"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { motion } from "framer-motion";
import { ArrowRight } from "lucide-react";
import { useAuth } from "@/components/auth-provider";
import { buttonVariants } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";

function getHomeRoute(role: string | undefined) {
  return role === "EMPLOYEE" ? "/employee" : "/dashboard";
}

const container = {
  hidden: {},
  show: {
    transition: {
      staggerChildren: 0.12,
    },
  },
};

const item = {
  hidden: { opacity: 0, y: 18 },
  show: {
    opacity: 1,
    y: 0,
    transition: {
      duration: 0.45,
      ease: [0.22, 1, 0.36, 1],
    },
  },
};

export default function LandingPage() {
  const router = useRouter();
  const { actor, ready } = useAuth();

  useEffect(() => {
    if (!ready || !actor) {
      return;
    }
    router.replace(getHomeRoute(actor.role));
  }, [actor, ready, router]);

  return (
    <motion.section
      variants={container}
      initial="hidden"
      animate="show"
      className="grid w-full max-w-4xl gap-5 md:grid-cols-2"
    >
      <motion.div variants={item}>
        <Card className="h-full rounded-[2rem] border border-border/70 bg-white/92 shadow-[0_20px_60px_rgba(36,32,28,0.08)]">
          <CardContent className="flex h-full flex-col justify-between gap-8 p-8 md:p-10">
            <div className="space-y-3">
              <p className="text-xs font-medium uppercase tracking-[0.24em] text-muted-foreground">Login</p>
              <h1 className="text-3xl font-semibold tracking-[-0.04em] text-foreground md:text-4xl">Welcome back</h1>
              <p className="text-sm leading-6 text-muted-foreground">
                Sign in with your verified `@gmail.com` account.
              </p>
            </div>
            <Link href="/login" className={buttonVariants({ variant: "default", size: "lg" })}>
              Open login
              <ArrowRight className="size-4" />
            </Link>
          </CardContent>
        </Card>
      </motion.div>

      <motion.div variants={item}>
        <Card className="brand-hero h-full rounded-[2rem] border border-border/70 shadow-[0_20px_60px_rgba(36,32,28,0.08)]">
          <CardContent className="flex h-full flex-col justify-between gap-8 p-8 md:p-10">
            <div className="space-y-3">
              <p className="text-xs font-medium uppercase tracking-[0.24em] text-muted-foreground">Register</p>
              <h2 className="text-3xl font-semibold tracking-[-0.04em] text-foreground md:text-4xl">Create access</h2>
              <p className="text-sm leading-6 text-muted-foreground">
                New accounts stay limited to `@gmail.com` and require email verification.
              </p>
            </div>
            <Link href="/register" className={buttonVariants({ variant: "outline", size: "lg" })}>
              Open register
              <ArrowRight className="size-4" />
            </Link>
          </CardContent>
        </Card>
      </motion.div>
    </motion.section>
  );
}
