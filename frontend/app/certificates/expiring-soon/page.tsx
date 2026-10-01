"use client";

import { ExpiryDashboard } from "@/components/admin/expiry-dashboard";
import { NO_ACCESS, StateMessage } from "@/components/instruments/state-message";
import { useAuth } from "@/lib/auth";

// Spec 19 §6.3: the same ExpiryDashboard admins see at /admin/certificates/expiring-soon, now
// also reachable for LM_OFFICER at a non-/admin path (an officer has no /admin page at all).
export default function OfficerExpiringSoonPage() {
  const { user } = useAuth();
  if (!user || user.role !== "LM_OFFICER") return <StateMessage title={NO_ACCESS} />;
  return <ExpiryDashboard />;
}
