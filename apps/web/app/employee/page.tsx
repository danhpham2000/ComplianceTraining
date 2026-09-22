"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import { useMemo, useState } from "react";
import { motion } from "framer-motion";
import { useQuery } from "@tanstack/react-query";
import { ArrowRight, Award, CalendarClock, CheckCircle2, Clock3, Download, PlayCircle } from "lucide-react";
import { useAuth } from "@/components/auth-provider";
import { EmptyState } from "@/components/empty-state";
import { MetricCard } from "@/components/metric-card";
import { usePersona } from "@/components/persona-provider";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Spinner } from "@/components/ui/spinner";
import { apiRequest, downloadApiFile } from "@/lib/api";
import { isCompleted, isDueSoon, sortAssignments } from "@/lib/assignments";
import { percent, shortDate } from "@/lib/format";
import { Assignment } from "@/lib/types";

export default function EmployeePage() {
  const { actor } = useAuth();
  const { persona } = usePersona();
  const assignments = useQuery({
    queryKey: ["my-assignments", persona.email],
    queryFn: () => apiRequest<Assignment[]>("/me/assignments"),
  });

  const items = useMemo(() => sortAssignments(assignments.data ?? []), [assignments.data]);
  const dueSoon = items.filter((assignment) => isDueSoon(assignment.due_at) && !isCompleted(assignment.status)).length;
  const completed = items.filter((assignment) => isCompleted(assignment.status)).length;
  const readyForQuiz = items.filter((assignment) => assignment.status === "QUIZ_READY").length;
  const nextAssignment = items.find((assignment) => !isCompleted(assignment.status)) ?? items[0];
  const upcomingAssignments = items.filter((assignment) => !isCompleted(assignment.status)).slice(0, 3);
  const certificates = items.filter((assignment) => assignment.certificate);
  const [downloadingId, setDownloadingId] = useState<string | null>(null);
  const [certificateError, setCertificateError] = useState<string | null>(null);

  async function handleDownload(assignment: Assignment) {
    if (!assignment.certificate) {
      return;
    }
    setCertificateError(null);
    setDownloadingId(assignment.id);
    try {
      await downloadApiFile(
        assignment.certificate.download_path,
        `nextphase-certificate-${assignment.training_title}.pdf`,
      );
    } catch (error) {
      setCertificateError(error instanceof Error ? error.message : "Could not download certificate.");
    } finally {
      setDownloadingId(null);
    }
  }

  if (assignments.isLoading) {
    return (
      <div className="flex min-h-[340px] items-center justify-center">
        <div className="flex items-center gap-3 text-sm text-muted-foreground">
          <Spinner className="size-5 text-primary" />
          Loading employee dashboard...
        </div>
      </div>
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.32, ease: "easeOut" }}
      className="space-y-5"
    >
      <section>
        <Card className="overflow-hidden rounded-[1.8rem] border-border/80">
          <CardContent className="p-0">
            <div className="flex flex-col gap-5 border-b border-border/70 bg-[linear-gradient(135deg,#ffffff,rgba(255,246,236,0.96))] px-5 py-5 md:flex-row md:items-end md:justify-between">
              <div className="max-w-2xl">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge variant="primary">Employee dashboard</Badge>
                </div>
                <h2 className="mt-3 text-[1.65rem] font-semibold tracking-[-0.05em] text-foreground md:text-[1.95rem]">
                  {nextAssignment?.training_title ?? "Your learning workspace"}
                </h2>
                <p className="mt-2 text-sm leading-6 text-[#6f819c]">
                  Keep the next required training visible, then open the full list when you want to continue.
                </p>
                <div className="mt-4 flex flex-wrap gap-3">
                  <InlineStat
                    label="Status"
                    value={nextAssignment?.status ?? "No assignments"}
                    icon={<CheckCircle2 className="size-4" />}
                  />
                  <InlineStat
                    label="Due"
                    value={nextAssignment?.due_at ? shortDate(nextAssignment.due_at, actor?.time_zone) : "No due date"}
                    icon={<CalendarClock className="size-4" />}
                  />
                  <InlineStat
                    label="Watch"
                    value={nextAssignment?.required_watch_percentage ? percent(nextAssignment.required_watch_percentage) : "Pending"}
                    icon={<Clock3 className="size-4" />}
                  />
                </div>
              </div>

              <div className="flex flex-wrap gap-3">
                <Button asChild className="h-11 px-5">
                  <Link href={nextAssignment ? `/learn/${nextAssignment.id}` : "/employee/training"}>
                    <PlayCircle className="size-4" />
                    {nextAssignment ? "Resume training" : "Open training"}
                  </Link>
                </Button>
                <Button asChild variant="outline" className="h-11 px-5">
                  <Link href="/employee/training">
                    View all training
                    <ArrowRight className="size-4" />
                  </Link>
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>
      </section>

      <section className="grid gap-4 md:grid-cols-4">
        <MetricCard label="Assigned" value={`${items.length}`} tone="accent" />
        <MetricCard label="Due soon" value={`${dueSoon}`} />
        <MetricCard label="Ready for quiz" value={`${readyForQuiz}`} />
        <MetricCard label="Completed" value={`${completed}`} tone="signal" />
      </section>

      <section>
        <Card className="rounded-[1.8rem] border-border/80">
          <CardHeader className="pb-4">
            <CardTitle className="text-[1.05rem]">Upcoming training</CardTitle>
            <CardDescription className="text-sm text-[#7b8ca5]">
              Continue the most relevant assignments from your queue.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            {upcomingAssignments.length ? (
              upcomingAssignments.map((assignment) => (
                <article key={assignment.id} className="rounded-[1.2rem] border border-border bg-[#fcfcfe] p-4">
                  <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <StatusCell status={assignment.status ?? "ASSIGNED"} />
                        <span className="text-xs font-medium text-[#7b8ca5]">
                          {assignment.due_at ? shortDate(assignment.due_at, actor?.time_zone) : "No due date"}
                        </span>
                      </div>
                      <p className="mt-3 truncate text-[15px] font-semibold text-foreground">{assignment.training_title}</p>
                      <p className="mt-1 text-sm text-muted-foreground">
                        {assignment.name} · Watch progress {percent(assignment.watch_percentage)}
                      </p>
                    </div>
                    <Button asChild size="sm" className="h-10 px-4 md:self-start">
                      <Link href={`/learn/${assignment.id}`}>
                        <PlayCircle className="size-4" />
                        Open
                      </Link>
                    </Button>
                  </div>
                </article>
              ))
            ) : (
              <EmptyState title="No assignments yet" body="Assigned training will appear here after an admin publishes a module." />
            )}
            {items.length ? (
              <Button asChild variant="outline" className="h-10 px-4">
                <Link href="/employee/training">
                  View full training list
                  <ArrowRight className="size-4" />
                </Link>
              </Button>
            ) : null}
          </CardContent>
        </Card>
      </section>

      <section>
        <Card className="rounded-[1.8rem] border-border/80">
          <CardHeader className="pb-4">
            <CardTitle className="text-[1.05rem]">Certificates</CardTitle>
            <CardDescription className="text-sm text-[#7b8ca5]">
              Completed training certificates stay available here for download.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            {certificates.length ? (
              certificates.map((assignment) => (
                <article key={assignment.id} className="rounded-[1.2rem] border border-border bg-[#fcfcfe] p-4">
                  <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="inline-flex items-center rounded-full bg-[#fff0df] px-3 py-1.5 text-xs font-semibold uppercase tracking-[0.14em] text-[#9f5818]">
                          <Award className="mr-1.5 size-3.5" />
                          Completed
                        </span>
                        <span className="text-xs font-medium text-[#7b8ca5]">
                          Issued {shortDate(assignment.certificate?.issued_at, actor?.time_zone)}
                        </span>
                      </div>
                      <p className="mt-3 truncate text-[15px] font-semibold text-foreground">{assignment.training_title}</p>
                      <p className="mt-1 text-sm text-muted-foreground">
                        {assignment.certificate?.certificate_number}
                      </p>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      <Button asChild size="sm" variant="outline" className="h-10 px-4">
                        <Link href={`/learn/${assignment.id}?tab=summary`}>Open summary</Link>
                      </Button>
                      <Button
                        type="button"
                        size="sm"
                        className="h-10 px-4"
                        disabled={downloadingId === assignment.id}
                        onClick={() => void handleDownload(assignment)}
                      >
                        {downloadingId === assignment.id ? <Spinner className="size-4" /> : <Download className="size-4" />}
                        {downloadingId === assignment.id ? "Preparing..." : "Download"}
                      </Button>
                    </div>
                  </div>
                </article>
              ))
            ) : (
              <EmptyState title="No certificates yet" body="Completed training certificates will appear here after you pass an assignment." />
            )}
            {certificateError ? <p className="text-sm text-destructive">{certificateError}</p> : null}
          </CardContent>
        </Card>
      </section>
    </motion.div>
  );
}

function InlineStat({
  icon,
  label,
  value,
}: {
  icon: ReactNode;
  label: string;
  value: string;
}) {
  return (
    <div className="min-w-[148px] rounded-[1rem] border border-border/80 bg-white/92 px-3.5 py-3">
      <div className="flex items-center gap-2 text-[#7d8ea6]">
        {icon}
        <span className="text-[11px] font-semibold uppercase tracking-[0.16em]">{label}</span>
      </div>
      <p className="mt-2 text-sm font-semibold text-foreground">{value}</p>
    </div>
  );
}

function StatusCell({ status }: { status: string }) {
  const accent = status === "COMPLETED" || status === "QUIZ_READY";
  return (
    <span
      className={
        accent
          ? "inline-flex w-fit items-center rounded-full bg-[#fff0df] px-3 py-1.5 text-xs font-semibold uppercase tracking-[0.14em] text-[#9f5818]"
          : "inline-flex w-fit items-center rounded-full bg-[#eef2f7] px-3 py-1.5 text-xs font-semibold uppercase tracking-[0.14em] text-[#708198]"
      }
    >
      {status}
    </span>
  );
}
