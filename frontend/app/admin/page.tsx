"use client";

import { ExpiryDashboard } from "@/components/admin/expiry-dashboard";
import { StateAdminDashboard } from "@/components/admin/state-admin-dashboard";
import { SuperAdminDashboard } from "@/components/admin/super-admin-dashboard";
import { NO_ACCESS, StateMessage } from "@/components/instruments/state-message";
import { useAuth } from "@/lib/auth";
import { ADMIN_ROLES } from "@/lib/types";

export default function AdminPage() {
  const { user } = useAuth();
  if (!user) return null;
  if (user.role === "SUPER_ADMIN") return <SuperAdminDashboard />;
  // Spec 18: STATE_ADMIN gets its own richer dashboard — checked before the generic ADMIN_ROLES
  // fallback below, since STATE_ADMIN is also a member of that set. DISTRICT_ADMIN is the only
  // role left falling through to the plain ExpiryDashboard now.
  if (user.role === "STATE_ADMIN") return <StateAdminDashboard />;
  if (ADMIN_ROLES.includes(user.role)) return <ExpiryDashboard />;
  return <StateMessage title={NO_ACCESS} />;
}
