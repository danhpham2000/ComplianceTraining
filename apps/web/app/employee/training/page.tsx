"use client";

import Link from "next/link";
import { useMemo, useState, type ReactNode } from "react";
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
import { isCompleted, isInProgress, isPastDue, sortAssignments } from "@/lib/assignments";
import { percent, shortDate } from "@/lib/format";
import { Assignment } from "@/lib/types";

export default function EmployeeTrainingPage() {
  const { actor } = useAuth();
  const { persona } = usePersona();
  const assignments = useQuery({
    queryKey: ["my-assignments", persona.email],
    queryFn: () => apiRequest<Assignment[]>("/me/assignments"),
  });

  const items = useMemo(() => sortAssignments(assignments.data ?? []), [assignments.data]);
  const nextAssignment = items.find((assignment) => !isCompleted(assignment.status)) ?? null;
  const assignedCount = items.length;
  const inProgressCount = items.filter((assignment) => isInProgress(assignment)).length;
  const readyForQuizCount = items.filter((assignment) => assignment.status === "QUIZ_READY").length;
  const completedCount = items.filter((assignment) => isCompleted(assignment.status)).length;
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
          Loading training list...
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
      <Card className="rounded-[1.8rem] border-border/80">
        <CardContent className="flex flex-col gap-5 bg-[linear-gradient(135deg,#ffffff,rgba(255,246,236,0.96))] px-5 py-5 md:flex-row md:items-end md:justify-between">
          <div className="max-w-2xl">
            <Badge variant="primary">Training queue</Badge>
            <h2 className="mt-3 text-[1.7rem] font-semibold tracking-[-0.05em] text-foreground md:text-[1.95rem]">
              Assigned training in one place
            </h2>
            <p className="mt-2 text-sm leading-6 text-[#6f819c]">
              Open any module, review its due date, and continue from the exact watch or quiz state already saved.
            </p>
          </div>
          <Button asChild variant="outline" className="h-11 px-5">
            <Link href="/employee">
              Dashboard
              <ArrowRight className="size-4" />
            </Link>
          </Button>
        </CardContent>
      </Card>

      <section className="grid gap-4 md:grid-cols-4">
        <MetricCard label="Assigned" value={`${assignedCount}`} tone="accent" />
        <MetricCard label="In progress" value={`${inProgressCount}`} />
        <MetricCard label="Ready for quiz" value={`${readyForQuizCount}`} />
        <MetricCard label="Completed" value={`${completedCount}`} tone="signal" />
      </section>

      <Card className="rounded-[1.8rem] border-border/80">
        <CardHeader className="pb-4">
          <CardTitle className="text-[1.05rem]">My training list</CardTitle>
          <CardDescription className="text-sm text-[#7b8ca5]">
            Click any assignment to continue the video, move into the quiz, or review the final result.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="hidden rounded-[1rem] border border-border bg-[#f8f9fc] px-4 py-3 text-[11px] font-semibold uppercase tracking-[0.18em] text-[#7b8ca5] md:grid md:grid-cols-[minmax(0,1.65fr)_140px_120px_120px_220px]">
            <span>Training</span>
            <span>Status</span>
            <span>Due date</span>
            <span>Progress</span>
            <span>Action</span>
          </div>

          {items.length ? (
            items.map((assignment) => (
              <article
                key={assignment.id}
                className="grid gap-3 rounded-[1.2rem] border border-border bg-[#fcfcfe] px-4 py-4 md:grid-cols-[minmax(0,1.65fr)_140px_120px_120px_220px] md:items-center"
              >
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <Link href={`/learn/${assignment.id}`} className="truncate text-[15px] font-semibold text-foreground hover:text-primary">
                      {assignment.training_title}
                    </Link>
                    {isPastDue(assignment.due_at, assignment.status) ? (
                      <span className="inline-flex items-center rounded-full bg-[#fff0df] px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.16em] text-[#ad5d12]">
                        Overdue
                      </span>
                    ) : null}
                  </div>
                  <p className="mt-1 truncate text-sm text-muted-foreground">{assignment.name}</p>
                </div>

                <StatusCell status={assignment.status ?? "ASSIGNED"} />

                <div className="space-y-1 text-sm text-[#66768f]">
                  <div className="flex items-center gap-2">
                    <CalendarClock className="size-4 text-[#8fa1b8]" />
                    <span>{assignment.due_at ? shortDate(assignment.due_at, actor?.time_zone) : "No due date"}</span>
                  </div>
                </div>

                <div className="space-y-1 text-sm text-[#66768f]">
                  <div className="flex items-center gap-2">
                    <Clock3 className="size-4 text-[#8fa1b8]" />
                    <span>{percent(assignment.watch_percentage)}</span>
                  </div>
                </div>

                <div className="flex flex-wrap gap-2 md:justify-self-start">
                  <Button asChild size="sm" className="h-10 px-4">
                    <Link href={`/learn/${assignment.id}`}>
                      {assignment.certificate ? <Award className="size-4" /> : <PlayCircle className="size-4" />}
                      {assignment.certificate ? "Open result" : "Open"}
                    </Link>
                  </Button>
                  {assignment.certificate ? (
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      className="h-10 px-4"
                      disabled={downloadingId === assignment.id}
                      onClick={() => void handleDownload(assignment)}
                    >
                      {downloadingId === assignment.id ? <Spinner className="size-4" /> : <Download className="size-4" />}
                      {downloadingId === assignment.id ? "Preparing..." : "Certificate"}
                    </Button>
                  ) : null}
                </div>
              </article>
            ))
          ) : (
            <EmptyState title="No training assigned" body="Published training will appear here as soon as it is assigned to your account." />
          )}
          {certificateError ? <p className="text-sm text-destructive">{certificateError}</p> : null}
        </CardContent>
      </Card>

      <section className="grid gap-5 lg:grid-cols-2">
        <Card className="rounded-[1.8rem] border-border/80">
          <CardHeader className="pb-4">
            <CardTitle className="text-[1.05rem]">How progression works</CardTitle>
            <CardDescription className="text-sm text-[#7b8ca5]">
              Each training keeps your watch and quiz state between visits.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <InfoRow icon={<PlayCircle className="size-4" />} text="Start with the video tab and reach the required watch threshold." />
            <InfoRow icon={<CheckCircle2 className="size-4" />} text="Quiz unlocks automatically once the watch requirement is met." />
            <InfoRow icon={<ArrowRight className="size-4" />} text="The summary tab records the final score and completion state." />
          </CardContent>
        </Card>

        <Card className="rounded-[1.8rem] border-border/80">
          <CardHeader className="pb-4">
            <CardTitle className="text-[1.05rem]">Quick access</CardTitle>
            <CardDescription className="text-sm text-[#7b8ca5]">
              Return to the dashboard or continue the first assignment still waiting on you.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <Button asChild className="h-11 w-full justify-between px-4">
              <Link href={nextAssignment ? `/learn/${nextAssignment.id}` : "/employee"}>
                Continue next training
                <ArrowRight className="size-4" />
              </Link>
            </Button>
            <Button asChild variant="outline" className="h-11 w-full justify-between px-4">
              <Link href="/settings">
                Open settings
                <ArrowRight className="size-4" />
              </Link>
            </Button>
          </CardContent>
        </Card>
      </section>
    </motion.div>
  );
}

function InfoRow({ icon, text }: { icon: ReactNode; text: string }) {
  return (
    <div className="flex items-center gap-3 rounded-[1.1rem] border border-border bg-[#fcfcfe] px-4 py-3 text-sm text-[#6f819c]">
      <div className="inline-flex size-8 items-center justify-center rounded-2xl bg-[#fff4e8] text-primary">{icon}</div>
      <span>{text}</span>
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
