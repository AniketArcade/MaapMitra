import type { Role } from "@api-types";

/** Roles the app serves. Admin roles are web-only; the backend enforces everything either way. */
export const MOBILE_ROLES: readonly Role[] = ["BUSINESS", "LM_OFFICER", "GATC"];

export function isMobileRole(role: Role): boolean {
  return MOBILE_ROLES.includes(role);
}

export function homeRouteFor(role: Role): "/(merchant)" | "/(officer)" | "/(gatc)" | null {
  if (role === "BUSINESS") return "/(merchant)";
  if (role === "LM_OFFICER") return "/(officer)";
  if (role === "GATC") return "/(gatc)";
  return null;
}
