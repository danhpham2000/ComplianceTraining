import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

const statusStyles = {
  READY: "border-emerald-200 bg-emerald-50 text-emerald-700",
  PUBLISHED: "border-blue-200 bg-blue-50 text-blue-700",
  PROCESSING: "border-amber-200 bg-amber-50 text-amber-700",
  DRAFT: "border-amber-200 bg-amber-50 text-amber-700",
  FAILED: "border-red-200 bg-red-50 text-red-700",
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

export function TrainingStatusBadge({ status }: { status?: string | null }) {
  const style = statusStyles[status as keyof typeof statusStyles] ?? statusStyles.DRAFT;

  return (
    <Badge className={cn("border px-3 py-1.5 text-xs font-semibold tracking-[0.08em]", style)}>
      {formatTrainingStatus(status)}
    </Badge>
  );
}
