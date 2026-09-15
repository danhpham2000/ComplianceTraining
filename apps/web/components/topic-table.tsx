import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { TopicMetric } from "@/lib/types";
import { percent } from "@/lib/format";

export function TopicTable({ topics }: { topics: TopicMetric[] }) {
  return (
    <Card className="rounded-[1.5rem]">
      <CardHeader>
        <CardTitle className="text-2xl">Weakest topics</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {topics.map((topic) => (
          <div key={topic.topic} className="rounded-[1.35rem] border border-border bg-[#fcfcfe] p-4">
            <div className="flex items-center justify-between gap-4">
              <div>
                <p className="font-semibold">{topic.topic}</p>
                <p className="text-sm text-muted-foreground">{topic.questions_answered} answers observed</p>
              </div>
              <div className="text-right text-sm">
                <p>First attempt {percent(topic.first_attempt_accuracy)}</p>
                <p>Final {percent(topic.final_accuracy)}</p>
              </div>
            </div>
            <div className="mt-3 flex items-center gap-3">
              <Progress value={Math.max(8, topic.final_accuracy)} className="flex-1" />
              <Badge variant="outline">{percent(topic.failure_rate)} fail</Badge>
            </div>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}
