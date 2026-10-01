"use client";

import { DistrictAdminDashboard } from "@/components/admin/district-admin-dashboard";
import { StateAdminDashboard } from "@/components/admin/state-admin-dashboard";
import { SuperAdminDashboard } from "@/components/admin/super-admin-dashboard";
import { NO_ACCESS, StateMessage } from "@/components/instruments/state-message";
import { useAuth } from "@/lib/auth";

// Spec 21: every ADMIN_ROLES member (SUPER_ADMIN, STATE_ADMIN, DISTRICT_ADMIN) now has its own
// dashboard — the old generic ExpiryDashboard fallback this page used to end on is gone; it's
// still reachable at /admin/certificates/expiring-soon for every admin role (and at
// /certificates/expiring-soon for LM_OFFICER).
export default function AdminPage() {
  const { user } = useAuth();
  if (!user) return null;
  if (user.role === "SUPER_ADMIN") return <SuperAdminDashboard />;
  if (user.role === "STATE_ADMIN") return <StateAdminDashboard />;
  if (user.role === "DISTRICT_ADMIN") return <DistrictAdminDashboard />;
  return <StateMessage title={NO_ACCESS} />;
}
