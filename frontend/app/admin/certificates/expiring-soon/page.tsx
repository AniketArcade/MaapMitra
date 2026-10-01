"use client";

import { ExpiryDashboard } from "@/components/admin/expiry-dashboard";
import { NO_ACCESS, StateMessage } from "@/components/instruments/state-message";
import { useAuth } from "@/lib/auth";
import { ADMIN_ROLES } from "@/lib/types";

export default function ExpiringSoonPage() {
  const { user } = useAuth();
  if (!user || !ADMIN_ROLES.includes(user.role)) return <StateMessage title={NO_ACCESS} />;
  return <ExpiryDashboard />;
}
