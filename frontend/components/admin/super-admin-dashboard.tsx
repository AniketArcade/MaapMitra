"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { StateOverviewTable } from "@/components/admin/state-overview-table";
import { Badge } from "@/components/ui/badge";
import { buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  api,
  getAdminCertificateStats,
  getApplicationStats,
  getAuditLogs,
  getGatcDirectory,
  getUsers,
} from "@/lib/api";
import { getApplicationMeta } from "@/lib/meta";
import { type Async, useAsync } from "@/lib/use-async";
import type { ApplicationMeta, Instrument, Page } from "@/lib/types";

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

function KpiCards() {
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
      {/* meta.statuses is already served in lifecycle order (DRAFT ... CERTIFICATE_ISSUED) */}
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

// Spec 17 §6.1: the SUPER_ADMIN-only dashboard. Each section is its own independent useAsync
// (own loading/error+retry/empty), same contract as the business/officer dashboards.
export function SuperAdminDashboard() {
  return (
    <div className="grid gap-6">
      <h1 className="text-2xl font-semibold">Super Admin</h1>
      <KpiCards />

      <div className="grid gap-3">
        <h2 className="text-lg font-medium">Verification overview</h2>
        <VerificationOverview />
      </div>

      <div className="grid gap-3">
        <h2 className="text-lg font-medium">State-wise overview</h2>
        <StateOverviewTable />
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
          <Link href="/admin/users" className={buttonVariants({ variant: "outline", size: "sm" })}>
            Create official account
          </Link>
        </div>
      </div>
    </div>
  );
}
