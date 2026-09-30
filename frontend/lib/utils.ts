export { cn } from "cn"

// Spec 15: display label for Inspection.assignee_role ("LM_OFFICER" | "GATC"). Raw enum, no
// meta-exposed label dict (see lib/types.ts's comment on Inspection.assignee_role) — shared here
// so the applications list/detail and the inspection wizard don't each retype the mapping.
export function assigneeRoleLabel(role: string): string {
  return role === "GATC" ? "GATC (test centre)" : "LM Officer";
}
