"use client";

import { DistrictOverviewTable } from "@/components/admin/district-overview-table";
import { NO_ACCESS, StateMessage } from "@/components/instruments/state-message";
import { useAuth } from "@/lib/auth";

// Spec 18 §6.2: no bespoke district-detail page — drill-down happens via the existing
// district-filterable pages (Applications, LMOs, GATCs), not a new one here.
export default function DistrictsPage() {
  const { user } = useAuth();
  if (!user || user.role !== "STATE_ADMIN") {
    return <StateMessage title={NO_ACCESS} />;
  }
  return (
    <div className="grid gap-6">
      <h1 className="text-2xl font-semibold">Districts</h1>
      <DistrictOverviewTable />
    </div>
  );
}
