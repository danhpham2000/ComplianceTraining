import { redirect } from "next/navigation";

export default async function LearnQuizRedirect({
  params,
}: {
  params: Promise<{ assignmentId: string }>;
}) {
  const { assignmentId } = await params;
  redirect(`/learn/${assignmentId}?tab=quiz`);
}
