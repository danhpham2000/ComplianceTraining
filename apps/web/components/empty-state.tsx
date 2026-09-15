import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export function EmptyState({ title, body }: { title: string; body: string }) {
  return (
    <Card className="rounded-[1.5rem]">
      <CardHeader>
        <CardTitle className="text-2xl">{title}</CardTitle>
      </CardHeader>
      <CardContent>
        <p className="max-w-xl text-sm text-muted-foreground">{body}</p>
      </CardContent>
    </Card>
  );
}
