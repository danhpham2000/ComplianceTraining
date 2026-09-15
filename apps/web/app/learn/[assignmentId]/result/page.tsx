import { redirect } from "next/navigation";

export default async function LearnResultRedirect({
  params,
}: {
  params: Promise<{ assignmentId: string }>;
}) {
  const { assignmentId } = await params;
  redirect(`/learn/${assignmentId}?tab=summary`);
}
