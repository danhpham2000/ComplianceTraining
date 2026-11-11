import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

const statusStyles = {
  READY: "border-emerald-200 bg-emerald-50 text-emerald-700 [&>span]:bg-emerald-500",
  PUBLISHED: "border-blue-200 bg-blue-50 text-blue-700 [&>span]:bg-blue-500",
  PROCESSING: "border-amber-200 bg-amber-50 text-amber-700 [&>span]:bg-amber-500",
  DRAFT: "border-amber-200 bg-amber-50 text-amber-700 [&>span]:bg-amber-500",
  FAILED: "border-red-200 bg-red-50 text-red-700 [&>span]:bg-red-500",
} as const;

export function formatTrainingStatus(status?: string | null) {
  switch (status) {
    case "DRAFT":
      return "Creating";
    case "PROCESSING":
      return "Processing";
    case "READY":
      return "Ready";
    case "PUBLISHED":
      return "Published";
    case "FAILED":
      return "Failed";
    default:
      return status ? status.charAt(0) + status.slice(1).toLowerCase() : "Creating";
  }
}

export function TrainingStatusBadge({ status, className }: { status?: string | null; className?: string }) {
  const style = statusStyles[status as keyof typeof statusStyles] ?? statusStyles.DRAFT;
  const label = formatTrainingStatus(status);

  return (
    <Badge
      className={cn("h-6 shrink-0 gap-1.5 border px-2.5 py-0 text-[10px] font-semibold tracking-[0.08em]", style, className)}
      aria-label={`Training status: ${label}`}
    >
      <span aria-hidden="true" className="size-1.5 rounded-full" />
      {label}
    </Badge>
  );
}
