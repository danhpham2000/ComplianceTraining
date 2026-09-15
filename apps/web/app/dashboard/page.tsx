"use client";

import { useState, type ReactNode } from "react";
import { motion } from "framer-motion";
import { useQuery } from "@tanstack/react-query";
import { Award, Download, Users } from "lucide-react";
import Link from "next/link";
import { EmptyState } from "@/components/empty-state";
import { MetricCard } from "@/components/metric-card";
import { usePersona } from "@/components/persona-provider";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Spinner } from "@/components/ui/spinner";
import { apiRequest, downloadApiFile } from "@/lib/api";
import { DirectoryUser, LearnerProgress, Training } from "@/lib/types";
import { percent, shortDate } from "@/lib/format";

export default function DashboardPage() {
  const { persona } = usePersona();
  const [page, setPage] = useState(1);
  const trainings = useQuery({
    queryKey: ["trainings", persona.email],
    queryFn: () => apiRequest<Training[]>("/training"),
    refetchInterval: (query) =>
      ((query.state.data as Training[] | undefined) ?? []).some((item) => item.status === "PROCESSING") ? 10000 : false,
  });
  const directory = useQuery({
    queryKey: ["directory", persona.email],
    queryFn: () => apiRequest<DirectoryUser[]>("/auth/directory"),
  });
  const learnerProgress = useQuery({
    queryKey: ["learner-progress", persona.email],
    queryFn: () => apiRequest<LearnerProgress[]>("/analytics/learner-progress"),
  });

  const trainingItems = trainings.data ?? [];
  const employeeItems = (directory.data ?? []).filter((item) => item.role === "EMPLOYEE");
  const progressItems = learnerProgress.data ?? [];
  const reviewCount = trainingItems.filter((item) => item.status !== "PUBLISHED").length;
  const publishedCount = trainingItems.filter((item) => item.status === "PUBLISHED").length;
  const completedAssignments = progressItems.filter((item) => item.status === "COMPLETED").length;
  const [downloadingCertificateId, setDownloadingCertificateId] = useState<string | null>(null);
  const [certificateError, setCertificateError] = useState<string | null>(null);

  const pageSize = 5;
  const pageCount = Math.max(1, Math.ceil(trainingItems.length / pageSize));
  const currentPage = Math.min(page, pageCount);
  const paginatedTrainings = trainingItems.slice((currentPage - 1) * pageSize, currentPage * pageSize);
  const visibleProgress = progressItems.slice(0, 8);

  async function handleCertificateDownload(item: LearnerProgress) {
    if (!item.certificate) {
      return;
    }
    setCertificateError(null);
    setDownloadingCertificateId(item.assignment_recipient_id);
    try {
      await downloadApiFile(
        item.certificate.download_path,
        `nextphase-certificate-${item.training_title}.pdf`,
      );
    } catch (error) {
      setCertificateError(error instanceof Error ? error.message : "Could not download certificate.");
    } finally {
      setDownloadingCertificateId(null);
    }
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.32, ease: "easeOut" }}
      className="space-y-4"
    >
      <section className="grid gap-3 md:grid-cols-4">
        <MetricCard label="Published" value={`${publishedCount}`} tone="accent" />
        <MetricCard label="In review" value={`${reviewCount}`} />
        <MetricCard label="Employees" value={`${employeeItems.length}`} />
        <MetricCard label="Completed" value={`${completedAssignments}`} tone="signal" />
      </section>

      <section>
        <Card className="rounded-[1.6rem] border-border/80">
          <CardHeader className="pb-3">
            <CardTitle className="text-base">Training library</CardTitle>
            <CardDescription className="text-[13px] text-[#7b8ca5]">
              Current training modules in this workspace.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="flex flex-wrap gap-2">
              <Button asChild className="h-9 px-4 text-sm">
                <Link href="/training/new">Build training</Link>
              </Button>
              <Button asChild variant="outline" className="h-9 px-4 text-sm">
                <Link href="/settings">Manage access</Link>
              </Button>
            </div>

            <div className="hidden rounded-[0.95rem] border border-border bg-[#f8f9fc] px-4 py-2.5 text-[10px] font-semibold uppercase tracking-[0.16em] text-[#7b8ca5] dark:bg-[#171f2b] dark:text-[#8fa1b8] md:grid md:grid-cols-[minmax(0,1.45fr)_120px_120px_40px]">
              <span>Module</span>
              <span>Status</span>
              <span>Questions</span>
              <span />
            </div>

            {paginatedTrainings.length ? (
              paginatedTrainings.map((training) => (
                <Link
                  key={training.id}
                  href={`/training/${training.id}`}
                  className="grid gap-2.5 rounded-[1rem] border border-border bg-white px-4 py-3 transition hover:border-primary/18 hover:bg-[#fffdf9] dark:bg-[#141a24] dark:hover:bg-[#1a2230] md:grid-cols-[minmax(0,1.45fr)_120px_120px_40px] md:items-center"
                >
                  <div className="min-w-0">
                    <p className="truncate text-sm font-semibold text-foreground">{training.title}</p>
                    <p className="mt-1 text-[13px] text-muted-foreground">
                      {training.content_source?.title ?? "Source attached during review"}
                    </p>
                  </div>
                  <CellPill tone={training.status === "PUBLISHED" ? "accent" : "neutral"}>
                    {formatTrainingStatus(training.status)}
                  </CellPill>
                  <span className="text-[13px] text-[#66768f] dark:text-[#8fa1b8]">{training.question_count} items</span>
                  <span className="text-right text-base text-[#a1adbc] dark:text-[#73839a]">›</span>
                </Link>
              ))
            ) : (
              <EmptyState title="No training yet" body="Use Build Training to create the first module." />
            )}

            {trainingItems.length > pageSize ? (
              <div className="flex flex-col gap-3 rounded-[1rem] border border-border bg-[#fcfcfe] px-4 py-3 dark:bg-[#141a24] md:flex-row md:items-center md:justify-between">
                <p className="text-[13px] text-muted-foreground">
                  Showing {Math.min((currentPage - 1) * pageSize + 1, trainingItems.length)}-{Math.min(currentPage * pageSize, trainingItems.length)} of{" "}
                  {trainingItems.length} training modules
                </p>
                <div className="flex items-center gap-2">
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    className="h-9 rounded-2xl px-4 text-sm"
                    disabled={currentPage === 1}
                    onClick={() => setPage((current) => Math.max(1, current - 1))}
                  >
                    Previous
                  </Button>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    className="h-9 rounded-2xl px-4 text-sm"
                    disabled={currentPage === pageCount}
                    onClick={() => setPage((current) => Math.min(pageCount, current + 1))}
                  >
                    Next
                  </Button>
                </div>
              </div>
            ) : null}
          </CardContent>
        </Card>
      </section>

      <section>
        <Card className="rounded-[1.6rem] border-border/80">
          <CardHeader className="pb-3">
            <CardTitle className="text-base">Employee progress</CardTitle>
            <CardDescription className="text-[13px] text-[#7b8ca5]">
              Review in-progress work, completed training, and certificate availability.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="hidden rounded-[0.95rem] border border-border bg-[#f8f9fc] px-4 py-2.5 text-[10px] font-semibold uppercase tracking-[0.16em] text-[#7b8ca5] md:grid md:grid-cols-[minmax(0,1.05fr)_minmax(0,1.2fr)_110px_110px_150px]">
              <span>Employee</span>
              <span>Training</span>
              <span>Status</span>
              <span>Score</span>
              <span>Certificate</span>
            </div>
            {learnerProgress.isLoading ? (
              <div className="flex min-h-[180px] items-center justify-center">
                <div className="flex items-center gap-3 text-sm text-muted-foreground">
                  <Spinner className="size-5 text-primary" />
                  Loading employee progress...
                </div>
              </div>
            ) : visibleProgress.length ? (
              visibleProgress.map((item) => (
                <article
                  key={item.assignment_recipient_id}
                  className="grid gap-3 rounded-[1rem] border border-border bg-[#fcfcfe] px-4 py-3 md:grid-cols-[minmax(0,1.05fr)_minmax(0,1.2fr)_110px_110px_150px] md:items-center"
                >
                  <div className="min-w-0">
                    <p className="truncate text-sm font-semibold text-foreground">{item.employee_name}</p>
                    <p className="mt-1 truncate text-[13px] text-muted-foreground">{item.employee_email}</p>
                  </div>
                  <div className="min-w-0">
                    <p className="truncate text-sm font-semibold text-foreground">{item.training_title}</p>
                    <p className="mt-1 truncate text-[13px] text-muted-foreground">
                      {item.completed_at
                        ? `Completed ${shortDate(item.completed_at)}`
                        : item.due_at
                          ? `Due ${shortDate(item.due_at)}`
                          : item.assignment_name}
                    </p>
                  </div>
                  <CellPill tone={item.status === "COMPLETED" ? "accent" : "neutral"}>{item.status}</CellPill>
                  <span className="text-[13px] text-[#66768f] dark:text-[#8fa1b8]">
                    {item.final_score != null ? percent(item.final_score) : "Pending"}
                  </span>
                  {item.certificate ? (
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      className="h-9 px-3"
                      disabled={downloadingCertificateId === item.assignment_recipient_id}
                      onClick={() => void handleCertificateDownload(item)}
                    >
                      {downloadingCertificateId === item.assignment_recipient_id ? (
                        <Spinner className="size-4" />
                      ) : (
                        <Download className="size-4" />
                      )}
                      {downloadingCertificateId === item.assignment_recipient_id ? "Preparing..." : "Download"}
                    </Button>
                  ) : (
                    <span className="inline-flex items-center gap-2 text-[13px] text-muted-foreground">
                      <Award className="size-4 text-[#b2bcc9]" />
                      Not issued
                    </span>
                  )}
                </article>
              ))
            ) : (
              <EmptyState title="No employee progress yet" body="Assigned training will appear here after an employee starts or completes a module." />
            )}
            {certificateError ? <p className="text-sm text-destructive">{certificateError}</p> : null}
          </CardContent>
        </Card>
      </section>

      <section>
        <Card className="rounded-[1.6rem] border-border/80">
          <CardHeader className="pb-3">
            <CardTitle className="text-base">Employee directory</CardTitle>
            <CardDescription className="text-[13px] text-[#7b8ca5]">
              Current employee accounts with active access.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            {employeeItems.length ? (
              employeeItems.map((employee) => (
                <div key={employee.id} className="rounded-[1rem] border border-border bg-[#fcfcfe] px-4 py-3 dark:bg-[#141a24]">
                  <div className="flex items-start gap-3">
                    <div className="inline-flex size-8 items-center justify-center rounded-xl bg-[#eef2f7] text-[#708198] dark:bg-[#1b2430] dark:text-[#8fa1b8]">
                      <Users className="size-3.5" />
                    </div>
                    <div className="min-w-0">
                      <p className="truncate text-sm font-semibold text-foreground">
                        {employee.name ?? employee.email}
                      </p>
                      <p className="mt-1 truncate text-[13px] text-muted-foreground">{employee.email}</p>
                    </div>
                  </div>
                </div>
              ))
            ) : (
              <div className="rounded-[1.2rem] border border-dashed border-border px-4 py-8 text-center text-sm text-muted-foreground">
                No employees have registered yet.
              </div>
            )}
          </CardContent>
        </Card>
      </section>
    </motion.div>
  );
}

function formatTrainingStatus(status: string) {
  if (status === "DRAFT") {
    return "IN REVIEW";
  }
  if (status === "PROCESSING") {
    return "BUILDING";
  }
  return status;
}

function CellPill({
  children,
  tone,
}: {
  children: ReactNode;
  tone: "accent" | "neutral";
}) {
  return (
    <span
      className={
        tone === "accent"
          ? "inline-flex w-fit items-center rounded-full bg-[#fff0df] px-3 py-1.5 text-xs font-semibold uppercase tracking-[0.14em] text-[#9f5818] dark:bg-[#2a1c10] dark:text-[#ffb25d]"
          : "inline-flex w-fit items-center rounded-full bg-[#eef2f7] px-3 py-1.5 text-xs font-semibold uppercase tracking-[0.14em] text-[#708198] dark:bg-[#1b2430] dark:text-[#8fa1b8]"
      }
    >
      {children}
    </span>
  );
}
