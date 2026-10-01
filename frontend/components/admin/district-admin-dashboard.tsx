"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useAuth } from "@/lib/auth";
import {
  api,
  getAdminCertificateStats,
  getApplicationStats,
  getAuditLogs,
  getDistrictOverview,
  getGatcDirectory,
  getUsers,
} from "@/lib/api";
import { getApplicationMeta, getInstrumentMeta } from "@/lib/meta";
import { type Async, useAsync } from "@/lib/use-async";
import type { ApplicationMeta, DistrictOverviewRow, Instrument, Page } from "@/lib/types";

function RetryError({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-3">
      <span className="text-sm text-muted-foreground">{message}</span>
      <button
        type="button"
        onClick={onRetry}
        className={buttonVariants({ variant: "outline", size: "sm" })}
      >
        Retry
      </button>
    </div>
  );
}

function useApplicationMeta(): ApplicationMeta | null {
  const [meta, setMeta] = useState<ApplicationMeta | null>(null);
  useEffect(() => {
    getApplicationMeta().then(setMeta, () => undefined);
  }, []);
  return meta;
}

function useStateName(stateCode: string | null): string | null {
  const [name, setName] = useState<string | null>(null);
  useEffect(() => {
    if (!stateCode) return;
    getInstrumentMeta().then(
      (meta) => setName(meta.regions.find((r) => r.state_code === stateCode)?.state_name ?? null),
      () => undefined,
    );
  }, [stateCode]);
  return name;
}

function KpiCards() {
  // Already district-scoped server-side (scope_instruments/scope_applications/
  // scope_certificates, and since spec 21 list_users()/gatc_directory() too, for a
  // DISTRICT_ADMIN caller) — verbatim reuse of the State/Super Admin dashboards' own KPI queries.
  const instruments = useAsync(() =>
    api<Page<Instrument>>("/instruments?page_size=1").then((p) => p.total),
  );
  const appStats = useAsync(() => getApplicationStats());
  const certStats = useAsync(() => getAdminCertificateStats());
  const activeLmos = useAsync(() =>
    getUsers(new URLSearchParams({ role: "LM_OFFICER", is_active: "true", page_size: "1" })).then(
      (p) => p.total,
    ),
  );
  const activeGatcs = useAsync(() =>
    getGatcDirectory(new URLSearchParams({ is_active: "true", page_size: "1" })).then(
      (p) => p.total,
    ),
  );

  const cards: { label: string; value: Async<number> }[] = [
    { label: "Instruments", value: instruments },
    { label: "Applications", value: { ...appStats, data: appStats.data?.total ?? null } },
    { label: "Certificates valid", value: { ...certStats, data: certStats.data?.valid ?? null } },
    {
      label: "Certificates expiring",
      value: { ...certStats, data: certStats.data?.expiring_soon ?? null },
    },
    { label: "Certificates expired", value: { ...certStats, data: certStats.data?.expired ?? null } },
    { label: "Active LMOs", value: activeLmos },
    { label: "Active GATCs", value: activeGatcs },
  ];

  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
      {cards.map((c) => (
        <Card key={c.label}>
          <CardHeader>
            <CardTitle className="text-2xl">
              {c.value.status === "loading" ? "…" : (c.value.data ?? 0)}
            </CardTitle>
          </CardHeader>
          <CardContent className="text-sm text-muted-foreground">{c.label}</CardContent>
        </Card>
      ))}
    </div>
  );
}

function VerificationOverview() {
  const stats = useAsync(() => getApplicationStats());
  const meta = useApplicationMeta();

  if (stats.status === "loading") {
    return <p className="text-sm text-muted-foreground">Loading…</p>;
  }
  if (stats.status === "error") {
    return <RetryError message="Couldn't load application counts." onRetry={stats.retry} />;
  }
  const by_status = stats.data?.by_status ?? {};
  return (
    <div className="flex flex-wrap gap-2">
      {(meta?.statuses ?? [])
        .filter((s) => by_status[s.value])
        .map((s) => (
          <Link
            key={s.value}
            href={`/admin/applications?status=${s.value}`}
            className="inline-flex min-h-11 items-center"
          >
            <Badge variant="secondary">
              {by_status[s.value]} {s.label}
            </Badge>
          </Link>
        ))}
    </div>
  );
}

// Spec 21 D2: the caller's own row of GET /admin/district-overview, rendered as a compact
// summary rather than the full zero-filled table a STATE_ADMIN sees (components/admin/
// district-overview-table.tsx) — a table of ~20 zero rows and one real one would read as "no
// data," not "not your jurisdiction," even though nothing actually leaks (every other district's
// row is genuinely zero through this caller's own scoping — see
// tests/test_admin_district_overview.py::test_district_admin_other_districts_zero_filled). Takes
// the shared getDistrictOverview() result as props (computed once in DistrictAdminDashboard)
// rather than fetching it again here.
function DistrictProfile({ overview, row }: { overview: Async<DistrictOverviewRow[]>; row: DistrictOverviewRow | undefined }) {
  if (overview.status === "loading") {
    return <p className="text-sm text-muted-foreground">Loading district profile…</p>;
  }
  if (overview.status === "error") {
    return <RetryError message="Couldn't load the district profile." onRetry={overview.retry} />;
  }
  if (!row) {
    return <p className="text-sm text-muted-foreground">District data unavailable.</p>;
  }
  return (
    <dl className="grid grid-cols-2 gap-x-6 gap-y-2 text-sm sm:grid-cols-4">
      <div>
        <dt className="text-muted-foreground">Instruments</dt>
        <dd className="text-lg font-medium">{row.instrument_count}</dd>
      </div>
      <div>
        <dt className="text-muted-foreground">Pending applications</dt>
        <dd className="text-lg font-medium">{row.pending_applications}</dd>
      </div>
      <div>
        <dt className="text-muted-foreground">Certificates valid</dt>
        <dd className="text-lg font-medium">{row.certs_valid}</dd>
      </div>
      <div>
        <dt className="text-muted-foreground">Certificates expired</dt>
        <dd className="text-lg font-medium">{row.certs_expired}</dd>
      </div>
    </dl>
  );
}

function RecentActivity() {
  const recent = useAsync(() => getAuditLogs(new URLSearchParams({ page_size: "5" })));

  if (recent.status === "loading") {
    return <p className="text-sm text-muted-foreground">Loading…</p>;
  }
  if (recent.status === "error") {
    return <RetryError message="Couldn't load recent activity." onRetry={recent.retry} />;
  }
  const items = recent.data?.items ?? [];
  if (items.length === 0) {
    return <p className="text-sm text-muted-foreground">No activity yet.</p>;
  }
  return (
    <ul className="grid gap-2">
      {items.map((row) => (
        <li key={row.id} className="flex items-center justify-between gap-3 text-sm">
          <span>
            <span className="font-medium">{row.actor_name ?? "System"}</span> — {row.action}
          </span>
          <span className="text-xs text-muted-foreground">
            {new Date(row.created_at).toLocaleString()}
          </span>
        </li>
      ))}
    </ul>
  );
}

// Spec 21 §6.1: the DISTRICT_ADMIN-only dashboard, one rank down from StateAdminDashboard. Reuses
// that dashboard's KPI/verification-overview/recent-activity sections verbatim (they're already
// district-scoped server-side once spec 21 §4's backend changes land) — the district-wise table
// becomes a single profile row (D2, no "Districts" drill-down makes sense for this role), and the
// heading/quick-actions are district-specific.
export function DistrictAdminDashboard() {
  const { user } = useAuth();
  const stateName = useStateName(user?.state_code ?? null);
  const overview = useAsync(() => getDistrictOverview());
  const ownRow = (overview.data ?? []).find((r) => r.district_code === user?.district_code);

  return (
    <div className="grid gap-6">
      <h1 className="text-2xl font-semibold">
        District Admin{ownRow ? ` — ${ownRow.district_name}` : ""}
        {stateName ? `, ${stateName}` : ""}
      </h1>
      <KpiCards />

      <div className="grid gap-3">
        <h2 className="text-lg font-medium">Verification overview</h2>
        <VerificationOverview />
      </div>

      <div className="grid gap-3">
        <h2 className="text-lg font-medium">District profile</h2>
        <DistrictProfile overview={overview} row={ownRow} />
      </div>

      <div className="grid gap-3">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-medium">Recent activity</h2>
          <Link href="/admin/audit-logs" className="text-sm underline">
            View all
          </Link>
        </div>
        <RecentActivity />
      </div>

      <div className="grid gap-3">
        <h2 className="text-lg font-medium">Quick actions</h2>
        <div className="flex flex-wrap gap-2">
          <Link
            href="/admin/applications?status=SUBMITTED"
            className={buttonVariants({ variant: "outline", size: "sm" })}
          >
            View pending applications
          </Link>
          <Link
            href="/admin/certificates/expiring-soon"
            className={buttonVariants({ variant: "outline", size: "sm" })}
          >
            View expiring certificates
          </Link>
          <Link href="/admin/audit-logs" className={buttonVariants({ variant: "outline", size: "sm" })}>
            View audit logs
          </Link>
        </div>
      </div>
    </div>
  );
}
