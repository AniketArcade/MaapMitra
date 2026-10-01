"use client";

import { ExpiryDashboard } from "@/components/admin/expiry-dashboard";
import { SuperAdminDashboard } from "@/components/admin/super-admin-dashboard";
import { NO_ACCESS, StateMessage } from "@/components/instruments/state-message";
import { useAuth } from "@/lib/auth";
import { ADMIN_ROLES } from "@/lib/types";

export default function AdminPage() {
  const { user } = useAuth();
  if (!user) return null;
  if (user.role === "SUPER_ADMIN") return <SuperAdminDashboard />;
  if (ADMIN_ROLES.includes(user.role)) return <ExpiryDashboard />;
  return <StateMessage title={NO_ACCESS} />;
}
