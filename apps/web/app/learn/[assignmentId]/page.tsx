"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import { motion } from "framer-motion";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { Award, CalendarClock, CirclePlay, Download, LockKeyhole } from "lucide-react";
import { useAuth } from "@/components/auth-provider";
import { CourseVideoPlayer } from "@/components/course-video-player";
import { EmptyState } from "@/components/empty-state";
import { MetricCard } from "@/components/metric-card";
import { usePersona } from "@/components/persona-provider";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Spinner } from "@/components/ui/spinner";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ApiError, apiRequest, downloadApiFile } from "@/lib/api";
import { percent, shortDate } from "@/lib/format";
import { AssignmentDetail, AttemptResult, QuizStart, ResultPayload } from "@/lib/types";
import { cn } from "@/lib/utils";

type LearningTab = "video" | "quiz" | "summary";
type VideoProgressPayload = {
  startSecond: number;
  endSecond: number;
  currentPositionSeconds: number;
  durationSeconds: number;
};
type VideoProgressResponse = {
  unique_watched_seconds: number;
  furthest_position_seconds: number;
  watch_percentage: number;
};

export default function LearnAssignmentPage() {
  const { assignmentId } = useParams<{ assignmentId: string }>();
  const router = useRouter();
  const searchParams = useSearchParams();
  const { actor } = useAuth();
  const { persona } = usePersona();
  const [activeTab, setActiveTab] = useState<LearningTab>("video");
  const [quiz, setQuiz] = useState<QuizStart | null>(null);
  const [selectedOption, setSelectedOption] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<AttemptResult | null>(null);
  const [localWatchPercentage, setLocalWatchPercentage] = useState<number | null>(null);
  const [videoCompleted, setVideoCompleted] = useState(false);
  const [certificateError, setCertificateError] = useState<string | null>(null);
  const hasResolvedInitialTab = useRef(false);
  const progressQueueRef = useRef<VideoProgressPayload[]>([]);
  const isFlushingProgressRef = useRef(false);

  const detailQuery = useQuery({
    queryKey: ["assignment-detail", assignmentId, persona.email],
    queryFn: () => apiRequest<AssignmentDetail>(`/me/assignments/${assignmentId}`, { email: persona.email }),
  });

  const detail = detailQuery.data;
  const watchPercentage = Math.max(detail?.watch_percentage ?? 0, localWatchPercentage ?? 0);
  const quizReady = Boolean(detail?.quiz_ready) || watchPercentage >= (detail?.required_watch_percentage ?? 100);
  const resultAvailable = detail?.status === "COMPLETED" || detail?.status === "FAILED";

  const resultQuery = useQuery({
    queryKey: ["assignment-result", assignmentId, persona.email],
    queryFn: () => apiRequest<ResultPayload>(`/me/assignments/${assignmentId}/result`, { email: persona.email }),
    enabled: activeTab === "summary" || resultAvailable,
  });

  useEffect(() => {
    if (!detail || hasResolvedInitialTab.current) {
      return;
    }
    const requested = searchParams.get("tab");
    const requestedTab =
      requested === "video" || requested === "quiz" || requested === "summary"
        ? requested
        : null;
    if (requestedTab === "summary" && resultAvailable) {
      updateTab("summary");
    } else if (requestedTab === "quiz" && quizReady) {
      updateTab("quiz");
    } else if (requestedTab === "video") {
      updateTab("video");
    } else if (resultAvailable) {
      updateTab("summary");
    } else if (quizReady) {
      updateTab("quiz");
    } else {
      updateTab("video");
    }
    hasResolvedInitialTab.current = true;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [detail, quizReady, resultAvailable, searchParams]);

  const startQuiz = useMutation({
    mutationFn: () =>
      apiRequest<QuizStart>(`/me/assignments/${assignmentId}/quiz/start`, {
        method: "POST",
        email: persona.email,
      }),
    onSuccess: (data) => setQuiz(data),
  });

  const submitAttempt = useMutation({
    mutationFn: () =>
      apiRequest<AttemptResult>(`/me/assignments/${assignmentId}/questions/${question?.id}/attempt`, {
        method: "POST",
        email: persona.email,
        body: {
          option_id: selectedOption,
          idempotency_key: crypto.randomUUID(),
        },
      }),
    onSuccess: (result) => {
      if (!quiz || !question) {
        return;
      }
      setFeedback(result);
      setQuiz({
        ...quiz,
        questions: quiz.questions.map((item) =>
          item.id === question.id
            ? {
                ...item,
                attempts_used: (item.attempts_used ?? 0) + 1,
                attempts_remaining: result.attempts_remaining,
                terminal: result.terminal,
              }
            : item,
        ),
      });
      setSelectedOption(null);
    },
  });

  const completeQuiz = useMutation({
    mutationFn: () =>
      apiRequest<ResultPayload>(`/me/assignments/${assignmentId}/quiz/complete`, {
        method: "POST",
        email: persona.email,
      }),
    onSuccess: async () => {
      await Promise.all([detailQuery.refetch(), resultQuery.refetch()]);
      updateTab("summary");
    },
  });
  const downloadCertificate = useMutation({
    mutationFn: async () => {
      const certificate = resultQuery.data?.certificate ?? detail?.certificate;
      if (!certificate) {
        throw new Error("Certificate is not available yet.");
      }
      await downloadApiFile(certificate.download_path, `nextphase-certificate-${detail?.training_title ?? "training"}.pdf`);
    },
    onError: (error) => {
      setCertificateError(error instanceof Error ? error.message : "Could not download certificate.");
    },
  });

  const questions = useMemo(() => quiz?.questions ?? [], [quiz?.questions]);
  const currentIndex = useMemo(() => questions.findIndex((item) => !item.terminal), [questions]);
  const question = currentIndex >= 0 ? questions[currentIndex] : null;

  useEffect(() => {
    if (activeTab !== "quiz" || !quizReady || quiz || startQuiz.isPending) {
      return;
    }
    startQuiz.mutate();
  }, [activeTab, quiz, quizReady, startQuiz]);

  function updateTab(nextTab: LearningTab) {
    setActiveTab(nextTab);
    router.replace(`/learn/${assignmentId}?tab=${nextTab}`, { scroll: false });
  }

  async function flushProgressQueue() {
    if (isFlushingProgressRef.current || !progressQueueRef.current.length || !detail) {
      return;
    }

    isFlushingProgressRef.current = true;
    try {
      while (progressQueueRef.current.length) {
        const payload = progressQueueRef.current.shift();
        if (!payload) {
          continue;
        }
        const response = await apiRequest<VideoProgressResponse>(`/me/assignments/${assignmentId}/video-progress`, {
          method: "POST",
          email: persona.email,
          body: {
            start_second: payload.startSecond,
            end_second: payload.endSecond,
            current_position_seconds: payload.currentPositionSeconds,
            duration_seconds: payload.durationSeconds,
          },
        });
        setLocalWatchPercentage(response.watch_percentage);
        if (response.watch_percentage >= detail.required_watch_percentage) {
          await detailQuery.refetch();
          updateTab("quiz");
          break;
        }
      }
    } finally {
      isFlushingProgressRef.current = false;
      if (progressQueueRef.current.length) {
        void flushProgressQueue();
      }
    }
  }

  function handleWatchProgress(payload: VideoProgressPayload) {
    if (quizReady) {
      return;
    }
    progressQueueRef.current.push(payload);
    void flushProgressQueue();
  }

  if (detailQuery.isLoading) {
    return (
      <div className="flex min-h-[360px] items-center justify-center">
        <div className="flex items-center gap-3 text-sm text-muted-foreground">
          <Spinner className="size-5 text-primary" />
          Loading training...
        </div>
      </div>
    );
  }

  if (detailQuery.error) {
    const isMissingAssignment = detailQuery.error instanceof ApiError && detailQuery.error.status === 404;
    return (
      <div className="space-y-4">
        <EmptyState
          title={isMissingAssignment ? "Training not found" : "Could not load training"}
          body={
            isMissingAssignment
              ? "This assignment is no longer available. It may have been deleted or removed from your workspace."
              : detailQuery.error.message
          }
        />
        <Button asChild variant="outline" className="h-10 px-4">
          <a href="/employee/training">Back to training list</a>
        </Button>
      </div>
    );
  }

  if (!detail) {
    return (
      <div className="space-y-4">
        <EmptyState
          title="Training unavailable"
          body="This assignment is not available right now."
        />
        <Button asChild variant="outline" className="h-10 px-4">
          <a href="/employee/training">Back to training list</a>
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
      <Card className="rounded-[1.9rem] border-border/80">
        <CardContent className="flex flex-col gap-5 bg-[linear-gradient(135deg,#ffffff,rgba(255,246,236,0.92))] p-5 lg:flex-row lg:items-end lg:justify-between">
          <div className="max-w-3xl">
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant="primary">Assigned training</Badge>
              <FlowPill label={detail.status ?? "ASSIGNED"} tone="accent" />
              <FlowPill
                label={detail.due_at ? `Due ${shortDate(detail.due_at, actor?.time_zone)}` : "No due date"}
                tone="neutral"
              />
            </div>
            <h2 className="mt-3 text-[1.8rem] font-semibold tracking-[-0.05em] text-foreground md:text-[2.05rem]">
              {detail.training_title}
            </h2>
            <p className="mt-2 text-sm leading-6 text-[#6f819c]">
              Watch the lesson, take the quiz, and review your official result in one workspace.
            </p>
          </div>

          <div className="grid gap-3 sm:grid-cols-3">
            <TopMetric label="Watch progress" value={percent(watchPercentage)} />
            <TopMetric label="Required watch" value={percent(detail.required_watch_percentage)} />
            <TopMetric label="Passing score" value={`${detail.passing_score}%`} />
          </div>
        </CardContent>
      </Card>

      <Tabs value={activeTab} onValueChange={(value: string) => updateTab(value as LearningTab)} className="space-y-5">
        <TabsList className="grid h-14 w-full max-w-[52rem] grid-cols-3 gap-2 rounded-[1.45rem] p-1.5">
          <TabsTrigger value="video" className="min-w-0 rounded-[1.1rem] text-[15px]">
            Video
          </TabsTrigger>
          <TabsTrigger
            value="quiz"
            disabled={!quizReady}
            className="min-w-0 rounded-[1.1rem] text-[15px] disabled:pointer-events-none disabled:opacity-45"
          >
            Take quiz
          </TabsTrigger>
          <TabsTrigger
            value="summary"
            disabled={!resultAvailable}
            className="min-w-0 rounded-[1.1rem] text-[15px] disabled:pointer-events-none disabled:opacity-45"
          >
            Summary result
          </TabsTrigger>
        </TabsList>

        <TabsContent value="video" className="space-y-5">
          <Card className="overflow-hidden rounded-[1.8rem] border-border/80">
            <CardHeader className="border-b border-border/70 bg-white px-5 py-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <CardTitle className="text-[1.05rem]">Lesson video</CardTitle>
                  <CardDescription className="mt-1 text-sm text-[#7b8ca5]">
                    Watch progress is tracked automatically while the video plays.
                  </CardDescription>
                </div>
                <div className="inline-flex items-center gap-2 rounded-full border border-border bg-[#f8fafc] px-3 py-1.5 text-xs font-semibold uppercase tracking-[0.18em] text-[#70819b]">
                  <CirclePlay className="size-3.5 text-primary" />
                  {formatDuration(detail.video_duration_seconds)}
                </div>
              </div>
            </CardHeader>
            <CardContent className="space-y-5 p-4 md:p-5">
              <CourseVideoPlayer
                url={detail.video_url}
                title={detail.video_title ?? detail.training_title ?? "Training video"}
                onWatchProgress={handleWatchProgress}
                onVideoComplete={() => {
                  setVideoCompleted(true);
                  void detailQuery.refetch();
                }}
              />

              <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_320px]">
                <Card className="rounded-[1.4rem] border-border/80 shadow-none">
                  <CardHeader className="pb-3">
                    <CardTitle className="text-base">Progress</CardTitle>
                    <CardDescription>Current watch status for this assignment.</CardDescription>
                  </CardHeader>
                  <CardContent className="space-y-4">
                    <div className="flex flex-wrap items-end justify-between gap-3">
                      <div>
                        <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[#9a7b5c]">Current watch</p>
                        <p className="mt-2 text-[1.9rem] font-semibold tracking-[-0.05em] text-foreground">
                          {percent(watchPercentage)}
                        </p>
                      </div>
                      <div className="rounded-full bg-[#fff4e8] px-3 py-1.5 text-xs font-semibold uppercase tracking-[0.14em] text-[#9f5818]">
                        {videoCompleted || watchPercentage >= 99 ? "Video complete" : quizReady ? "Quiz unlocked" : "Watching"}
                      </div>
                    </div>

                    <Progress value={Math.max(4, watchPercentage)} />
                    <div className="flex flex-wrap gap-3 text-sm text-[#66768f]">
                      <span>Required watch percentage: {percent(detail.required_watch_percentage)}</span>
                      <span>Playback is saved automatically.</span>
                    </div>

                    {quizReady ? (
                      <div className="rounded-[1.2rem] border border-primary/15 bg-[#fff8ef] px-4 py-4">
                        <p className="text-sm font-semibold text-[#8a5723]">Video threshold reached</p>
                        <p className="mt-1 text-sm leading-6 text-[#8a5723]">
                          You can continue to the quiz tab now.
                        </p>
                      </div>
                    ) : null}
                  </CardContent>
                </Card>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="quiz" className="space-y-5">
          {!quizReady ? (
            <LockedCard
              icon={<LockKeyhole className="size-4" />}
              title="Quiz locked"
              body="Complete the required watch percentage in the video tab before the quiz becomes available."
            />
          ) : startQuiz.isPending && !quiz ? (
            <LockedCard
              icon={<Spinner className="size-4 text-primary" />}
              title="Preparing quiz"
              body="Loading the assessment for this training."
            />
          ) : !question && questions.length ? (
            <Card className="rounded-[1.8rem] border-border/80">
              <CardHeader>
                <Badge variant="primary" className="w-fit">Quiz complete</Badge>
                <CardTitle className="text-[1.9rem] tracking-[-0.05em]">All questions are finished</CardTitle>
                <CardDescription>Submit the quiz to calculate the official result.</CardDescription>
              </CardHeader>
              <CardContent>
                <Button onClick={() => completeQuiz.mutate()} disabled={completeQuiz.isPending} className="h-11 px-5">
                  {completeQuiz.isPending ? <Spinner className="size-4" /> : null}
                  {completeQuiz.isPending ? "Finishing..." : "Finish and score"}
                </Button>
              </CardContent>
            </Card>
          ) : (
            <Card className="rounded-[1.8rem] border-border/80">
              <CardHeader className="space-y-3">
                <Badge variant="primary" className="w-fit">Quiz</Badge>
                <CardTitle className="text-[1.9rem] tracking-[-0.05em]">
                  {question ? `Question ${currentIndex + 1} of ${questions.length}` : "Loading quiz..."}
                </CardTitle>
                <CardDescription>Answer each question to move this assignment to a final result.</CardDescription>
              </CardHeader>
              <CardContent>
                {question ? (
                  <>
                    <div className="rounded-[1.4rem] border border-border bg-[#fcfcfe] p-5">
                      <p className="text-base font-semibold leading-7 text-foreground">{question.text}</p>
                      <p className="mt-2 text-[11px] uppercase tracking-[0.18em] text-[#9a7b5c]">{question.topic}</p>
                    </div>

                    <div className="mt-4 space-y-3">
                      {question.options.map((option) => (
                        <button
                          key={option.id}
                          type="button"
                          onClick={() => setSelectedOption(option.id)}
                          className={cn(
                            "block w-full rounded-[1.2rem] border px-4 py-4 text-left text-sm transition",
                            selectedOption === option.id
                              ? "border-primary/35 bg-[#fff7ef]"
                              : "border-border bg-white hover:border-primary/18 hover:bg-[#fffdf9]",
                          )}
                        >
                          {option.text}
                        </button>
                      ))}
                    </div>

                    <div className="mt-5 flex flex-wrap items-center gap-4">
                      <Button
                        onClick={() => submitAttempt.mutate()}
                        disabled={!selectedOption || submitAttempt.isPending}
                        className="h-11 px-5"
                      >
                        {submitAttempt.isPending ? <Spinner className="size-4" /> : null}
                        {submitAttempt.isPending ? "Submitting..." : "Submit answer"}
                      </Button>
                      <p className="text-sm text-muted-foreground">
                        Attempts remaining: {question.attempts_remaining}
                      </p>
                    </div>

                    {feedback ? (
                      <div className="mt-5 rounded-[1.2rem] border border-border bg-secondary/30 p-5 text-sm">
                        <p className="font-semibold">{feedback.correct ? "Correct." : "Incorrect."}</p>
                        {feedback.message ? <p className="mt-2 text-muted-foreground">{feedback.message}</p> : null}
                      </div>
                    ) : null}
                  </>
                ) : null}
              </CardContent>
            </Card>
          )}
        </TabsContent>

        <TabsContent value="summary" className="space-y-5">
          {!resultAvailable && !resultQuery.data ? (
            <LockedCard
              icon={<CalendarClock className="size-4" />}
              title="Summary unavailable"
              body="Finish the quiz first. The official result appears here after submission."
            />
          ) : resultQuery.isLoading && !resultQuery.data ? (
            <LockedCard
              icon={<Spinner className="size-4 text-primary" />}
              title="Loading summary"
              body="Preparing the final training result."
            />
          ) : (
            <>
              <Card className="rounded-[1.8rem] brand-hero">
                <CardHeader>
                  <Badge variant="primary" className="w-fit">Official result</Badge>
                  <CardTitle className="text-[2.1rem] tracking-[-0.05em]">
                    {resultQuery.data?.status ?? "Pending"}
                  </CardTitle>
                  <CardDescription>
                    Completed {shortDate(resultQuery.data?.completed_at, actor?.time_zone)}
                  </CardDescription>
                </CardHeader>
              </Card>

              <section className="grid gap-4 md:grid-cols-4">
                <MetricCard label="Official score" value={percent(resultQuery.data?.official_score)} tone="accent" />
                <MetricCard label="Passing score" value={percent(resultQuery.data?.passing_score)} />
                <MetricCard label="First attempt" value={percent(resultQuery.data?.first_attempt_accuracy)} />
                <MetricCard label="Video completion" value={percent(resultQuery.data?.video_completion_percentage)} tone="signal" />
              </section>

              {resultQuery.data?.certificate ? (
                <Card className="rounded-[1.8rem] border-border/80">
                  <CardContent className="flex flex-col gap-4 p-5 md:flex-row md:items-center md:justify-between">
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <Badge variant="primary">Certificate ready</Badge>
                        <span className="text-xs font-medium text-[#7b8ca5]">
                          Issued {shortDate(resultQuery.data.certificate.issued_at, actor?.time_zone)}
                        </span>
                      </div>
                      <h3 className="mt-3 flex items-center gap-2 text-[1.1rem] font-semibold text-foreground">
                        <Award className="size-5 text-primary" />
                        Completion certificate
                      </h3>
                      <p className="mt-1 text-sm text-muted-foreground">
                        {resultQuery.data.certificate.certificate_number}
                      </p>
                    </div>
                    <Button
                      type="button"
                      className="h-11 px-5"
                      disabled={downloadCertificate.isPending}
                      onClick={() => {
                        setCertificateError(null);
                        downloadCertificate.mutate();
                      }}
                    >
                      {downloadCertificate.isPending ? <Spinner className="size-4" /> : <Download className="size-4" />}
                      {downloadCertificate.isPending ? "Preparing..." : "Download certificate"}
                    </Button>
                  </CardContent>
                </Card>
              ) : null}
              {certificateError ? <p className="text-sm text-destructive">{certificateError}</p> : null}

              <section className="grid gap-5 xl:grid-cols-2">
                <Card className="rounded-[1.6rem] border-border/80">
                  <CardHeader>
                    <CardTitle className="text-[1.05rem]">Strengths</CardTitle>
                    <CardDescription>Topics handled well on the final result.</CardDescription>
                  </CardHeader>
                  <CardContent className="flex flex-wrap gap-2">
                    {resultQuery.data?.summary?.strengths?.map((item) => (
                      <span key={item} className="rounded-full bg-secondary px-3 py-2 text-sm text-secondary-foreground">
                        {item}
                      </span>
                    ))}
                  </CardContent>
                </Card>

                <Card className="rounded-[1.6rem] border-border/80">
                  <CardHeader>
                    <CardTitle className="text-[1.05rem]">Needs improvement</CardTitle>
                    <CardDescription>Areas to revisit from the training.</CardDescription>
                  </CardHeader>
                  <CardContent>
                    <div className="flex flex-wrap gap-2">
                      {resultQuery.data?.summary?.needs_improvement?.map((item) => (
                        <span key={item} className="rounded-full bg-accent px-3 py-2 text-sm text-accent-foreground">
                          {item}
                        </span>
                      ))}
                    </div>
                    <p className="mt-4 text-sm leading-6 text-muted-foreground">
                      {resultQuery.data?.summary?.summary}
                    </p>
                  </CardContent>
                </Card>
              </section>
            </>
          )}
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

function TopMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-[1.15rem] border border-white/70 bg-white/80 px-4 py-3.5 shadow-sm backdrop-blur">
      <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[#9a7b5c]">{label}</p>
      <p className="mt-2 text-sm font-semibold text-foreground md:text-[15px]">{value}</p>
    </div>
  );
}

function FlowPill({ label, tone }: { label: string; tone: "accent" | "neutral" }) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-3 py-1.5 text-xs font-semibold uppercase tracking-[0.16em]",
        tone === "accent" ? "bg-[#fff0df] text-[#9f5818]" : "bg-white/80 text-[#6f819c]",
      )}
    >
      {label}
    </span>
  );
}

function LockedCard({ icon, title, body }: { icon: ReactNode; title: string; body: string }) {
  return (
    <Card className="rounded-[1.8rem] border-border/80">
      <CardContent className="flex min-h-[220px] flex-col items-center justify-center gap-3 text-center">
        <div className="inline-flex size-10 items-center justify-center rounded-2xl bg-[#fff4e8] text-primary">
          {icon}
        </div>
        <h3 className="text-lg font-semibold text-foreground">{title}</h3>
        <p className="max-w-lg text-sm leading-6 text-muted-foreground">{body}</p>
      </CardContent>
    </Card>
  );
}
