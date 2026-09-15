"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import type { ReactNode } from "react";
import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { CheckCircle2 } from "lucide-react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm, useWatch } from "react-hook-form";
import { z } from "zod";
import { usePersona } from "@/components/persona-provider";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Spinner } from "@/components/ui/spinner";
import { apiRequest } from "@/lib/api";
import { Training } from "@/lib/types";

const schema = z.object({
  researchQuery: z.string().min(6),
  generationMode: z.enum(["LECTURE", "CARTOON"]),
  questionCount: z.coerce.number().min(3).max(12),
});

type FormValues = z.infer<typeof schema>;

function getProcessingSteps(mode: "LECTURE" | "CARTOON") {
  return [
    {
      title: "Researching live sources",
      body: "Finding recent guidance, best practices, and reference material for the topic.",
    },
    {
      title: "Structuring the lesson",
      body: "Turning the research into a focused training outline and narrated script.",
    },
    {
      title: mode === "CARTOON" ? "Generating animation" : "Rendering lecture visuals",
      body:
        mode === "CARTOON"
          ? "Creating a native animated training clip with Sora from the generated lesson script and scene direction."
          : "Preparing the lecture-style lesson frames for the final video.",
    },
    {
      title: "Assembling training package",
      body: "Building the lesson video and pairing it with the first quiz set.",
    },
  ] as const;
}

export default function TrainingBuilderPage() {
  const router = useRouter();
  const { persona } = usePersona();
  const [buildStage, setBuildStage] = useState<"idle" | "processing">("idle");
  const [activeStep, setActiveStep] = useState(0);
  const trainings = useQuery({
    queryKey: ["trainings", persona.email],
    queryFn: () => apiRequest<Training[]>("/training"),
    refetchInterval: (query) =>
      ((query.state.data as Training[] | undefined) ?? []).some((item) => item.status === "PROCESSING") ? 10000 : false,
  });
  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      researchQuery: "",
      generationMode: "LECTURE",
      questionCount: 6,
    },
  });
  const questionCount = useWatch({ control: form.control, name: "questionCount" });
  const generationMode = useWatch({ control: form.control, name: "generationMode" });
  const processingSteps = getProcessingSteps(generationMode);

  const mutation = useMutation({
    mutationFn: async (values: FormValues) => {
      setBuildStage("processing");
      setActiveStep(0);
      return apiRequest<Training>("/training/research-build", {
        method: "POST",
        email: persona.email,
        body: {
          research_query: values.researchQuery,
          generation_mode: values.generationMode,
          question_count: values.questionCount,
        },
      });
    },
    onSuccess: async (data) => {
      setBuildStage("idle");
      setActiveStep(0);
      await trainings.refetch();
      router.push(`/training/${data.id}`);
    },
    onError: () => {
      setBuildStage("idle");
      setActiveStep(0);
    },
  });

  useEffect(() => {
    if (!mutation.isPending) {
      return;
    }

    const interval = window.setInterval(() => {
      setActiveStep((current) => Math.min(current + 1, processingSteps.length - 1));
    }, 6000);

    return () => window.clearInterval(interval);
  }, [mutation.isPending, processingSteps.length]);

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.32, ease: "easeOut" }}
      className="space-y-5"
    >
      <section className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_320px]">
        <Card className="rounded-[1.8rem] border-border/80">
          <CardHeader className="pb-3">
            <CardTitle className="text-base">Build training</CardTitle>
            <CardDescription className="text-[13px] text-[#7b8ca5]">
              Enter one research topic. The system will use that topic as the training title, research the latest material, and build the lesson automatically.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form className="space-y-4" onSubmit={form.handleSubmit((values) => mutation.mutate(values))}>
              <div className="grid gap-4 md:grid-cols-2">
                <Field label="Research topic" error={form.formState.errors.researchQuery?.message}>
                  <Input
                    className="h-11"
                    placeholder="Security awareness best practices for remote employees"
                    {...form.register("researchQuery")}
                  />
                </Field>
                <Field label="Video format" error={form.formState.errors.generationMode?.message}>
                  <Select
                    value={generationMode}
                    onValueChange={(value: "LECTURE" | "CARTOON") =>
                      form.setValue("generationMode", value, { shouldValidate: true })
                    }
                  >
                    <SelectTrigger className="h-11 rounded-2xl">
                      <SelectValue placeholder="Select video format" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="LECTURE">Lecture (Slide)</SelectItem>
                      <SelectItem value="CARTOON">Animation (Cartoon)</SelectItem>
                    </SelectContent>
                  </Select>
                </Field>
              </div>
              <div className="grid gap-4 md:grid-cols-2">
                <Field label="Question count" error={form.formState.errors.questionCount?.message}>
                  <Select
                    value={String(questionCount)}
                    onValueChange={(value: string) => form.setValue("questionCount", Number(value), { shouldValidate: true })}
                  >
                    <SelectTrigger className="h-11 rounded-2xl">
                      <SelectValue placeholder="Select question count" />
                    </SelectTrigger>
                    <SelectContent>
                      {[3, 4, 5, 6, 7, 8, 9, 10, 11, 12].map((count) => (
                        <SelectItem key={count} value={String(count)}>
                          {count} questions
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </Field>
              </div>
              <div className="flex flex-wrap gap-3">
                <Button type="submit" disabled={mutation.isPending} className="h-11 px-5">
                  {mutation.isPending ? <Spinner className="size-4" /> : null}
                  {mutation.isPending ? "Queueing..." : "Create from research"}
                </Button>
                <Button asChild variant="outline" className="h-11 px-5">
                  <Link href="/dashboard">Back to dashboard</Link>
                </Button>
              </div>

              {mutation.isPending ? (
                <Card className="rounded-[1.45rem] border-primary/15 bg-[linear-gradient(180deg,#fffaf3,rgba(255,245,232,0.84))] shadow-none">
                  <CardContent className="space-y-4 p-5">
                    <div className="flex items-start gap-3">
                      <div className="flex size-10 shrink-0 items-center justify-center rounded-full bg-white shadow-sm">
                        <Spinner className="size-4 text-primary" />
                      </div>
                      <div>
                        <p className="text-sm font-semibold text-foreground">Processing workflow</p>
                        <p className="mt-1 text-sm leading-6 text-[#7b654d]">
                          {buildStage === "processing"
                            ? generationMode === "CARTOON"
                              ? "The system is building the training in sequence. Research, narration, video generation, and final assembly may take a little longer."
                              : "The system is building the training in sequence. This can take a little longer while research, narration, and video assembly complete."
                            : null}
                        </p>
                      </div>
                    </div>

                    <div className="space-y-3">
                      {processingSteps.map((step, index) => {
                        const status =
                          index < activeStep ? "complete" : index === activeStep ? "current" : "upcoming";
                        return (
                          <motion.div
                            key={step.title}
                            initial={{ opacity: 0, y: 8 }}
                            animate={{ opacity: 1, y: 0 }}
                            transition={{ duration: 0.22, delay: index * 0.04 }}
                            className="flex items-start gap-3 rounded-[1.1rem] border border-white/80 bg-white/80 px-4 py-3"
                          >
                            <div className="mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-full border border-border bg-white">
                              {status === "complete" ? (
                                <CheckCircle2 className="size-4 text-primary" />
                              ) : status === "current" ? (
                                <Spinner className="size-3.5 text-primary" />
                              ) : (
                                <span className="text-[11px] font-semibold text-[#97a3b6]">{index + 1}</span>
                              )}
                            </div>
                            <div className="min-w-0">
                              <p className="text-sm font-semibold text-foreground">{step.title}</p>
                              <p className="mt-1 text-sm leading-6 text-[#73829a]">{step.body}</p>
                            </div>
                          </motion.div>
                        );
                      })}
                    </div>
                  </CardContent>
                </Card>
              ) : null}

              {mutation.error ? (
                <div className="rounded-[1.5rem] border border-primary/20 bg-accent p-5 text-sm text-accent-foreground">
                  {mutation.error.message}
                </div>
              ) : null}
            </form>
          </CardContent>
        </Card>

        <Card className="rounded-[1.8rem] border-border/80">
          <CardHeader className="pb-4">
            <CardTitle className="text-[1.05rem]">Library snapshot</CardTitle>
            <CardDescription className="text-sm text-[#7b8ca5]">
              Training modules in the current workspace.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            {(trainings.data ?? []).slice(0, 5).length ? (
              (trainings.data ?? []).slice(0, 5).map((training) => (
                <Link
                  key={training.id}
                  href={`/training/${training.id}`}
                  className="block rounded-[1.15rem] border border-border bg-[#fcfcfe] px-4 py-4 transition hover:border-primary/20 hover:bg-[#fffaf4] dark:bg-[#141a24] dark:hover:bg-[#1a2230]"
                >
                  <p className="text-sm font-semibold text-foreground">{training.title}</p>
                  <p className="mt-1 text-sm text-muted-foreground">
                    {formatTrainingStatus(training.status)} · {training.question_count} questions
                  </p>
                </Link>
              ))
            ) : (
              <div className="rounded-[1.2rem] border border-dashed border-border px-4 py-8 text-center text-sm text-muted-foreground">
                No training yet. Create the first module here.
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

function Field({
  label,
  error,
  children,
}: {
  label: string;
  error?: string;
  children: ReactNode;
}) {
  return (
    <label className="block">
      <span className="mb-2 block text-sm font-medium text-foreground">{label}</span>
      {children}
      {error ? <span className="mt-2 block text-sm text-destructive">{error}</span> : null}
    </label>
  );
}
