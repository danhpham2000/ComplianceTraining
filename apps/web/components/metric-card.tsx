import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";

type Props = {
  label: string;
  value: string;
  tone?: "default" | "accent" | "signal";
};

export function MetricCard({ label, value, tone = "default" }: Props) {
  const toneClass =
    tone === "accent"
      ? "border-primary/18 bg-[linear-gradient(180deg,rgba(255,246,236,0.95),rgba(255,255,255,0.95))]"
      : tone === "signal"
        ? "border-[#404040]/10 bg-[linear-gradient(180deg,rgba(248,249,252,0.95),rgba(255,255,255,0.95))]"
        : "bg-[linear-gradient(180deg,rgba(255,255,255,0.98),rgba(251,252,254,0.98))]";

  return (
    <Card className={cn("rounded-[1.2rem] shadow-[0_14px_38px_rgba(31,24,16,0.05)]", toneClass)}>
      <CardContent className="p-4">
        <Badge variant={tone === "accent" ? "primary" : "outline"} className="mb-3 text-[10px]">
          {label}
        </Badge>
        <p className="text-[1.55rem] font-semibold tracking-[-0.03em] text-foreground">{value}</p>
      </CardContent>
    </Card>
  );
}
