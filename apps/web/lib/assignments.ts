import { Assignment } from "@/lib/types";

export function isCompleted(status?: string | null) {
  return status === "COMPLETED";
}

export function isDueSoon(dueAt?: string | null) {
  if (!dueAt) {
    return false;
  }
  const delta = new Date(dueAt).getTime() - Date.now();
  return delta >= 0 && delta <= 1000 * 60 * 60 * 24 * 7;
}

export function isInProgress(assignment: Assignment) {
  return !isCompleted(assignment.status) && (assignment.status === "IN_PROGRESS" || (assignment.watch_percentage ?? 0) > 0);
}

export function isPastDue(dueAt?: string | null, status?: string | null) {
  return dueAt ? !isCompleted(status) && new Date(dueAt).getTime() < Date.now() : false;
}

export function sortAssignments(assignments: Assignment[]) {
  return [...assignments].sort((left, right) => {
    if (isCompleted(left.status) !== isCompleted(right.status)) {
      return isCompleted(left.status) ? 1 : -1;
    }
    return assignmentSortValue(left) - assignmentSortValue(right);
  });
}

function assignmentSortValue(assignment: Assignment) {
  return assignment.due_at ? new Date(assignment.due_at).getTime() : Number.MAX_SAFE_INTEGER;
}
