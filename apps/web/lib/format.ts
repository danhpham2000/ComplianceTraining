export function percent(value: number | null | undefined) {
  return `${Math.round(value ?? 0)}%`;
}

export function shortDate(value: string | null | undefined, timeZone?: string | null) {
  if (!value) {
    return "No due date";
  }
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    timeZone: timeZone ?? undefined,
  }).format(new Date(value));
}
