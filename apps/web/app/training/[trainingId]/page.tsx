"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { motion } from "framer-motion";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useParams, useRouter } from "next/navigation";
import { CheckCircle2, Send, Trash2, Users } from "lucide-react";
import { CourseVideoPlayer } from "@/components/course-video-player";
import { EmptyState } from "@/components/empty-state";
import { usePersona } from "@/components/persona-provider";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ConfirmationDialog } from "@/components/ui/confirmation-dialog";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Spinner } from "@/components/ui/spinner";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ApiError, apiRequest } from "@/lib/api";
import { cn } from "@/lib/utils";
import { DirectoryUser, Training } from "@/lib/types";

export default function TrainingDetailPage() {
  const { trainingId } = useParams<{ trainingId: string }>();
  const router = useRouter();
  const queryClient = useQueryClient();
  const { persona } = usePersona();
  const [audience, setAudience] = useState<"all" | "specific">("all");
  const [selectedEmployeeId, setSelectedEmployeeId] = useState<string>("");
  const [activeCitationSection, setActiveCitationSection] = useState<string | null>(null);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);

  const query = useQuery({
    queryKey: ["training", trainingId, persona.email],
    queryFn: () => apiRequest<Training>(`/training/${trainingId}`),
    refetchInterval: (request) =>
      (request.state.data as Training | undefined)?.status === "PROCESSING" ? 10000 : false,
  });
  const directory = useQuery({
    queryKey: ["directory", persona.email],
    queryFn: () => apiRequest<DirectoryUser[]>("/auth/directory"),
  });

  const employees = useMemo(
    () => (directory.data ?? []).filter((user) => user.role === "EMPLOYEE" && user.status === "ACTIVE"),
    [directory.data],
  );

  const publish = useMutation({
    mutationFn: () =>
      apiRequest<Training>(`/training/${trainingId}/publish`, {
        method: "POST",
        body: {
          assign_to_all: audience === "all",
          recipient_user_ids: audience === "specific" && selectedEmployeeId ? [selectedEmployeeId] : [],
        },
    }),
    onSuccess: () => query.refetch(),
  });
  const removeTraining = useMutation({
    mutationFn: () =>
      apiRequest<{ message: string }>(`/training/${trainingId}`, {
        method: "DELETE",
      }),
    onSuccess: async () => {
      setDeleteDialogOpen(false);
      queryClient.removeQueries({ queryKey: ["training", trainingId, persona.email] });
      queryClient.setQueryData<Training[]>(["trainings", persona.email], (current) =>
        (current ?? []).filter((item) => item.id !== trainingId),
      );
      await queryClient.invalidateQueries({ queryKey: ["trainings", persona.email] });
      router.push("/dashboard");
    },
  });

  const training = query.data;
  const isPublished = training?.status === "PUBLISHED";
  const isProcessing = training?.status === "PROCESSING";
  const isFailed = training?.status === "FAILED";

  if (query.isLoading) {
    return (
      <div className="flex min-h-[340px] items-center justify-center">
        <div className="flex items-center gap-3 text-sm text-muted-foreground">
          <Spinner className="size-5 text-primary" />
          Loading training...
        </div>
      </div>
    );
  }

  if (query.isError) {
    const notFound = query.error instanceof ApiError && query.error.status === 404;
    return (
      <div className="space-y-4">
        <EmptyState
          title={notFound ? "Training not found" : "Could not load training"}
          body={
            notFound
              ? "This training was deleted or is no longer available in the workspace."
              : query.error instanceof Error
                ? query.error.message
                : "The training could not be loaded."
          }
        />
        <Button asChild className="h-10 px-4">
          <Link href="/dashboard">Back to dashboard</Link>
        </Button>
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
      <ConfirmationDialog
        open={deleteDialogOpen}
        onOpenChange={setDeleteDialogOpen}
        title="Delete this training?"
        description="This removes the training, its assignments, and learner progress. This action cannot be undone."
        confirmLabel="Delete training"
        isPending={removeTraining.isPending}
        onConfirm={() => removeTraining.mutate()}
      />

      <Card className="rounded-[1.9rem] border-border/80">
        <CardContent className="flex flex-col gap-5 bg-[linear-gradient(135deg,#ffffff,rgba(255,246,236,0.92))] p-5 dark:bg-[linear-gradient(135deg,#141a24,rgba(42,28,16,0.92))] lg:flex-row lg:items-end lg:justify-between">
          <div className="max-w-3xl">
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant="primary">Training review</Badge>
              <StatusPill label={formatTrainingStatus(training?.status)} tone="neutral" />
              <StatusPill label={`${training?.question_count ?? 0} questions`} tone="accent" />
            </div>
            <h2 className="mt-3 text-[1.8rem] font-semibold tracking-[-0.05em] text-foreground md:text-[2.05rem]">
              {training?.title ?? "Loading training..."}
            </h2>
            <p className="mt-2 text-sm leading-6 text-[#6f819c] dark:text-[#97a8be]">
              Review the video first, then switch to question approval and publish controls.
            </p>
          </div>

          <div className="grid gap-3 sm:grid-cols-2">
            <TopMetric label="Questions" value={`${training?.question_count ?? 0}`} />
            <TopMetric label="Active employees" value={`${employees.length}`} />
            <Button
              type="button"
              variant="outline"
              className="h-[54px] rounded-[1.15rem] border-destructive/20 bg-white/80 px-4 text-destructive shadow-sm sm:col-span-2"
              disabled={removeTraining.isPending}
              onClick={() => setDeleteDialogOpen(true)}
            >
              {removeTraining.isPending ? <Spinner className="size-4" /> : <Trash2 className="size-4" />}
              {removeTraining.isPending ? "Deleting..." : "Delete training"}
            </Button>
          </div>
        </CardContent>
      </Card>

      {isProcessing ? (
        <Card className="rounded-[1.6rem] border-primary/15 bg-[linear-gradient(180deg,#fffaf3,rgba(255,245,232,0.82))]">
          <CardContent className="flex items-start gap-3 p-5">
            <div className="flex size-10 shrink-0 items-center justify-center rounded-full bg-white shadow-sm">
              <Spinner className="size-4 text-primary" />
            </div>
            <div className="min-w-0">
              <p className="text-sm font-semibold text-foreground">Training build in progress</p>
              <p className="mt-1 text-sm leading-6 text-[#7b654d]">
                This module is being generated in the background. You can leave this page and keep working. A notification will appear when the training is ready.
              </p>
            </div>
          </CardContent>
        </Card>
      ) : null}

      {isFailed ? (
        <Card className="rounded-[1.6rem] border-destructive/15 bg-[linear-gradient(180deg,#fff8f6,rgba(255,244,241,0.9))]">
          <CardContent className="space-y-2 p-5">
            <p className="text-sm font-semibold text-foreground">Training build failed</p>
            <p className="text-sm leading-6 text-[#7b654d]">
              {training?.description || "The workflow could not complete. Review the configuration and try again."}
            </p>
          </CardContent>
        </Card>
      ) : null}

      <Tabs defaultValue="source" className="space-y-5">
        <div className="flex justify-start">
          <TabsList className="grid h-14 w-full max-w-[68rem] grid-cols-4 gap-2 rounded-[1.45rem] p-1.5">
            <TabsTrigger value="source" className="min-w-0 rounded-[1.1rem] text-[15px]">
              Source video
            </TabsTrigger>
            <TabsTrigger value="material" className="min-w-0 rounded-[1.1rem] text-[15px]">
              Material
            </TabsTrigger>
            <TabsTrigger value="questions" className="min-w-0 rounded-[1.1rem] text-[15px]">
              Question bank
            </TabsTrigger>
            <TabsTrigger value="publish" className="min-w-0 rounded-[1.1rem] text-[15px]">
              Publish
            </TabsTrigger>
          </TabsList>
        </div>

        <TabsContent value="source" className="space-y-5">
          <Card className="overflow-hidden rounded-[1.8rem] border-border/80">
            <CardHeader className="border-b border-border/70 bg-white px-5 py-4 dark:bg-[#171f2b]">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <CardTitle className="text-[1.05rem]">Source video</CardTitle>
                  <CardDescription className="mt-1 text-sm text-[#7b8ca5]">
                    Review the lesson in a broad stage before approving downstream content.
                  </CardDescription>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <StatusPill
                    label={formatDuration(training?.content_source?.duration_seconds)}
                    tone="neutral"
                  />
                  {training?.content_source?.source_url ? (
                    <Button asChild variant="outline" className="h-10 rounded-full px-4">
                      <Link href={training.content_source.source_url} target="_blank" rel="noreferrer">
                        Open source
                      </Link>
                    </Button>
                  ) : null}
                </div>
              </div>
            </CardHeader>
            <CardContent className="space-y-4 p-4 md:p-5">
              {training?.content_source?.source_url ? (
                <CourseVideoPlayer
                  url={training.content_source.source_url}
                  title={training.content_source.title ?? training.title ?? "Training video"}
                  fallbackLabel="Open source video"
                />
              ) : (
                <div className="flex min-h-[420px] items-center justify-center rounded-[1.6rem] border border-border bg-[#f6f8fc] px-10 text-center">
                  <div>
                    {isProcessing ? <Spinner className="mx-auto size-10 text-primary" /> : null}
                    <p className="mt-4 text-base font-medium text-foreground">
                      {isProcessing ? "Video generation is still running" : isFailed ? "Video is not available" : "Video is not attached yet"}
                    </p>
                    <p className="mt-2 text-sm leading-6 text-muted-foreground">
                      {isProcessing
                        ? "The lesson video will appear here automatically when the background workflow finishes."
                        : isFailed
                          ? "The training build did not finish, so there is no video to review yet."
                          : "The lesson source will appear here after the training package is ready."}
                    </p>
                  </div>
                </div>
              )}

              <div className="grid gap-3 md:grid-cols-3">
                <InfoMetric label="Status" value={formatTrainingStatus(training?.status)} />
                <InfoMetric label="Question count" value={`${training?.question_count ?? 0}`} />
                <InfoMetric label="Video title" value={training?.content_source?.title ?? (isProcessing ? "Generating now" : "Not available")} />
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="material" className="space-y-5">
          <section className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_320px]">
            <Card className="rounded-[1.8rem] border-border/80">
              <CardHeader className="pb-4">
                <CardTitle className="text-[1.05rem]">Research material</CardTitle>
                <CardDescription className="text-sm text-[#7b8ca5]">
                  Review the crawl result that was turned into the lesson and quiz.
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                {training?.research_material?.query ? (
                  <div className="rounded-[1.15rem] border border-border bg-[#fcfcfe] px-4 py-4 dark:bg-[#141a24]">
                    <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[#9a7b5c]">Research topic</p>
                    <p className="mt-2 text-sm font-semibold text-foreground">{training.research_material.query}</p>
                  </div>
                ) : null}

                {training?.research_material?.overview ? (
                  <div className="rounded-[1.15rem] border border-border bg-[#fcfcfe] px-4 py-4 dark:bg-[#141a24]">
                    <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[#9a7b5c]">Overview</p>
                    <p className="mt-2 text-sm leading-6 text-foreground">{training.research_material.overview}</p>
                  </div>
                ) : null}

                <div className="space-y-4">
                  {(training?.research_material?.sections ?? []).map((section, index) => (
                    <article
                      key={`${section.title}-${index}`}
                      className="rounded-[1.25rem] border border-border bg-[#fcfcfe] p-5 dark:bg-[#141a24]"
                    >
                      <div className="flex flex-wrap items-center gap-2">
                        <Badge variant="primary">{`Section ${index + 1}`}</Badge>
                        <div
                          className="relative"
                          onMouseEnter={() => setActiveCitationSection(`${section.title}-${index}`)}
                          onMouseLeave={() => setActiveCitationSection((current) => (current === `${section.title}-${index}` ? null : current))}
                        >
                          <button
                            type="button"
                            onFocus={() => setActiveCitationSection(`${section.title}-${index}`)}
                            onBlur={() => setActiveCitationSection((current) => (current === `${section.title}-${index}` ? null : current))}
                            className="rounded-full"
                            aria-label={`Show ${section.citations.length} sources for ${section.title}`}
                          >
                            <Badge variant="outline">{section.citations.length} sources</Badge>
                          </button>
                          <div
                            className={cn(
                              "pointer-events-none absolute left-full top-1/2 z-20 ml-3 w-[20rem] -translate-y-1/2 rounded-[1.15rem] border border-border bg-white p-3 shadow-[0_18px_40px_rgba(31,24,16,0.14)] transition-all duration-150 dark:bg-[#171f2b]",
                              activeCitationSection === `${section.title}-${index}`
                                ? "translate-x-0 opacity-100"
                                : "translate-x-1 opacity-0",
                            )}
                          >
                            <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[#9a7b5c]">
                              Section sources
                            </p>
                            <div className="mt-3 space-y-2">
                              {section.citations.map((citation) => (
                                <Link
                                  key={citation}
                                  href={citation}
                                  target="_blank"
                                  rel="noreferrer"
                                  className="pointer-events-auto block rounded-[0.95rem] border border-border bg-[#fcfcfe] px-3 py-2.5 transition-colors hover:border-primary/30 hover:bg-[#fff7ef] dark:bg-[#141a24]"
                                >
                                  <p className="text-xs font-semibold text-foreground">{formatSourceLabel(citation)}</p>
                                  <p className="mt-1 truncate text-xs text-[#6f819c]">{citation}</p>
                                </Link>
                              ))}
                            </div>
                          </div>
                        </div>
                      </div>
                      <h4 className="mt-3 text-base font-semibold text-foreground md:text-[17px]">{section.title}</h4>
                      <p className="mt-2 text-sm leading-6 text-[#6f819c]">{section.summary}</p>
                      {section.bullets.length ? (
                        <div className="mt-4 grid gap-2">
                          {section.bullets.map((bullet) => (
                            <div key={bullet} className="rounded-[1rem] border border-border bg-white px-4 py-3 text-sm leading-6 text-foreground dark:bg-[#171f2b]">
                              {bullet}
                            </div>
                          ))}
                        </div>
                      ) : null}
                    </article>
                  ))}
                </div>
              </CardContent>
            </Card>

            <Card className="rounded-[1.8rem] border-border/80">
              <CardHeader className="pb-4">
                <CardTitle className="text-[1.05rem]">Source list</CardTitle>
                <CardDescription className="text-sm text-[#7b8ca5]">
                  Distinct links captured from the research crawl.
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-3">
                {(training?.research_material?.sources ?? []).map((source) => (
                  <Link
                    key={source.url}
                    href={source.url}
                    target="_blank"
                    rel="noreferrer"
                    className="block rounded-[1.1rem] border border-border bg-[#fcfcfe] px-4 py-4 transition-colors hover:bg-white dark:bg-[#141a24] dark:hover:bg-[#171f2b]"
                  >
                    <p className="text-sm font-semibold text-foreground">{source.title}</p>
                    <p className="mt-1 text-xs uppercase tracking-[0.16em] text-[#9a7b5c]">{source.domain ?? "Source"}</p>
                    <p className="mt-2 truncate text-sm text-muted-foreground">{source.url}</p>
                  </Link>
                ))}
              </CardContent>
            </Card>
          </section>
        </TabsContent>

        <TabsContent value="questions" className="space-y-5">
          <Card className="rounded-[1.8rem] border-border/80">
            <CardHeader className="pb-4">
              <CardTitle className="text-[1.05rem]">Question bank</CardTitle>
              <CardDescription className="text-sm text-[#7b8ca5]">
                Review and approve the generated assessment separately from the source video.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="grid gap-4 lg:grid-cols-[250px_minmax(0,1fr)]">
                <div className="rounded-[1.3rem] border border-border bg-[#fcfcfe] p-3 dark:bg-[#141a24]">
                  <div className="max-h-[32rem] space-y-2 overflow-y-auto pr-1">
                    {training?.questions?.map((question, index) => (
                      <div key={question.id} className="rounded-[1.05rem] border border-border bg-white px-3 py-3 dark:bg-[#171f2b]">
                        <div className="flex items-center gap-2">
                          <span className="inline-flex size-7 items-center justify-center rounded-full bg-[#fff2e4] text-xs font-semibold text-primary dark:bg-[#2a1c10]">
                            {index + 1}
                          </span>
                          <div className="min-w-0">
                            <p className="truncate text-sm font-semibold text-foreground">{question.topic ?? "Review item"}</p>
                            <p className="truncate text-xs text-muted-foreground">{question.options.length} options</p>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>

                <div className="max-h-[32rem] space-y-4 overflow-y-auto pr-1">
                  {training?.questions?.map((question) => (
                    <article key={question.id} className="rounded-[1.35rem] border border-border bg-[#fcfcfe] p-5 dark:bg-[#141a24]">
                      <div className="flex flex-wrap items-center gap-2">
                        <Badge variant="outline">{question.topic ?? "General"}</Badge>
                        <Badge variant="primary">{formatQuestionStatus(question.status)}</Badge>
                      </div>
                      <h4 className="mt-3 text-base font-semibold leading-7 text-foreground md:text-[17px]">
                        {question.text}
                      </h4>
                      <div className="mt-4 grid gap-2">
                        {question.options.map((option) => (
                          <div
                            key={option.id}
                            className={cn(
                              "rounded-[1rem] border px-4 py-3 text-sm leading-6",
                              option.is_correct
                                ? "border-primary/20 bg-[#fff3e6] text-[#6d4518] dark:bg-[#2a1c10] dark:text-[#ffd5ab]"
                                : "border-border bg-white text-foreground dark:bg-[#171f2b]",
                            )}
                          >
                            {option.text}
                          </div>
                        ))}
                      </div>
                    </article>
                  ))}
                </div>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="publish" className="space-y-5">
          <section className="grid gap-5 xl:grid-cols-[minmax(0,0.95fr)_380px]">
            <Card className="rounded-[1.8rem] border-border/80">
              <CardHeader className="pb-4">
                <CardTitle className="text-[1.05rem]">Publish audience</CardTitle>
                <CardDescription className="text-sm text-[#7b8ca5]">
                  Choose exactly who receives the training when you publish.
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="space-y-2">
                  <label className="text-sm font-medium">Delivery mode</label>
                  <Select value={audience} onValueChange={(value: "all" | "specific") => setAudience(value)}>
                    <SelectTrigger className="h-11 rounded-2xl bg-white dark:bg-[#171f2b]">
                      <SelectValue placeholder="Select delivery mode" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">All active employees</SelectItem>
                      <SelectItem value="specific">Specific employee</SelectItem>
                    </SelectContent>
                  </Select>
                </div>

                {audience === "specific" ? (
                  <div className="space-y-2">
                    <label className="text-sm font-medium">Employee</label>
                    <Select value={selectedEmployeeId} onValueChange={setSelectedEmployeeId}>
                      <SelectTrigger className="h-11 rounded-2xl bg-white dark:bg-[#171f2b]">
                        <SelectValue placeholder="Select employee" />
                      </SelectTrigger>
                      <SelectContent>
                        {employees.map((employee) => (
                          <SelectItem key={employee.id} value={employee.id}>
                            {employee.name ?? employee.email}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                ) : null}

                <Button
                  onClick={() => publish.mutate()}
                  disabled={
                    !training ||
                    training.status !== "READY" ||
                    isPublished ||
                    publish.isPending ||
                    (audience === "specific" && !selectedEmployeeId)
                  }
                  className="h-12 w-full rounded-2xl"
                >
                  {publish.isPending ? <Spinner className="size-4" /> : <Send className="size-4" />}
                  {publish.isPending ? "Publishing..." : isPublished ? "Published" : "Publish and send"}
                </Button>
                {isPublished ? (
                  <p className="text-sm text-muted-foreground">
                    This training is already published and cannot be published again.
                  </p>
                ) : isProcessing ? (
                  <p className="text-sm text-muted-foreground">
                    Publish becomes available after the background build completes.
                  </p>
                ) : isFailed ? (
                  <p className="text-sm text-muted-foreground">
                    This training did not finish building. Review the error above and create a new build when ready.
                  </p>
                ) : null}
              </CardContent>
            </Card>

            <div className="space-y-5">
              <Card className="rounded-[1.8rem] border-border/80">
                <CardHeader className="pb-4">
                  <CardTitle className="text-[1.05rem]">Learning objectives</CardTitle>
                  <CardDescription className="text-sm text-[#7b8ca5]">
                    Scope to confirm before it reaches employees.
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-3">
                  {training?.learning_objectives?.map((objective) => (
                    <div key={objective.id} className="rounded-[1.1rem] border border-border bg-[#fcfcfe] px-4 py-4 dark:bg-[#141a24]">
                      <div className="flex gap-3">
                        <CheckCircle2 className="mt-0.5 size-4 text-primary" />
                        <p className="text-sm leading-6 text-foreground">{objective.text}</p>
                      </div>
                    </div>
                  ))}
                </CardContent>
              </Card>

              <Card className="rounded-[1.8rem] border-border/80">
                <CardHeader className="pb-4">
                  <CardTitle className="text-[1.05rem]">Active employees</CardTitle>
                  <CardDescription className="text-sm text-[#7b8ca5]">
                    Users who can receive this training right now.
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-3">
                  {employees.map((employee) => (
                    <div key={employee.id} className="rounded-[1.1rem] border border-border bg-[#fcfcfe] px-4 py-4 dark:bg-[#141a24]">
                      <div className="flex items-start gap-3">
                        <div className="inline-flex size-9 items-center justify-center rounded-2xl bg-[#fff2e4] text-primary dark:bg-[#2a1c10]">
                          <Users className="size-4" />
                        </div>
                        <div className="min-w-0">
                          <p className="truncate text-sm font-semibold text-foreground">{employee.name ?? employee.email}</p>
                          <p className="mt-1 truncate text-sm text-muted-foreground">{employee.email}</p>
                        </div>
                      </div>
                    </div>
                  ))}
                </CardContent>
              </Card>
            </div>
          </section>
        </TabsContent>
      </Tabs>
    </motion.div>
  );
}

function formatDuration(seconds?: number | null) {
  if (!seconds) {
    return "Pending";
  }
  const minutes = Math.floor(seconds / 60);
  const remaining = seconds % 60;
  return `${minutes}:${String(remaining).padStart(2, "0")}`;
}

function formatTrainingStatus(status?: string | null) {
  if (!status) {
    return "Loading";
  }
  if (status === "DRAFT") {
    return "IN REVIEW";
  }
  if (status === "PROCESSING") {
    return "BUILDING";
  }
  return status;
}

function formatQuestionStatus(status?: string | null) {
  if (!status || status === "DRAFT") {
    return "REVIEW";
  }
  return status;
}

function formatSourceLabel(url: string) {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

function TopMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-[1.15rem] border border-white/70 bg-white/80 px-4 py-3.5 shadow-sm backdrop-blur dark:border-[#283243] dark:bg-[#171f2b]/90">
      <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[#9a7b5c]">{label}</p>
      <p className="mt-2 text-sm font-semibold text-foreground md:text-[15px]">{value}</p>
    </div>
  );
}

function InfoMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-[1.1rem] border border-border bg-[#fcfcfe] px-4 py-4 dark:bg-[#141a24]">
      <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[#9a7b5c]">{label}</p>
      <p className="mt-2 text-sm font-semibold text-foreground">{value}</p>
    </div>
  );
}

function StatusPill({
  label,
  tone,
}: {
  label: string;
  tone: "accent" | "neutral";
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-3 py-1.5 text-xs font-semibold uppercase tracking-[0.16em]",
        tone === "accent"
          ? "bg-[#fff0df] text-[#9f5818] dark:bg-[#2a1c10] dark:text-[#ffb25d]"
          : "bg-white/80 text-[#6f819c] dark:bg-[#171f2b] dark:text-[#97a8be]",
      )}
    >
      {label}
    </span>
  );
}
