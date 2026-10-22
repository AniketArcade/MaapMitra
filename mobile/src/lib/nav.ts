import type { Role } from "@api-types";
import { router, type Href } from "expo-router";

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

/**
 * Opens a screen inside another tab's stack with that tab's list (the layout's anchor) underneath,
 * so Back always reaches the list. A bare router.push into an unmounted tab stack would leave the
 * detail as the only screen, with nothing to go back to.
 */
export function openInTab(target: Href): void {
  router.push(target, { withAnchor: true });
}
