"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { StatusBadge } from "@/components/applications/status-badge";
import { Badge } from "@/components/ui/badge";
import { buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { api, getAdminCertificateStats, getApplicationStats } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { getApplicationMeta, labelFor } from "@/lib/meta";
import { type Async, useAsync } from "@/lib/use-async";
import {
  ADMIN_ROLES,
  type AdminCertificateStats,
  type Application,
  type ApplicationMeta,
  type ApplicationStats,
  type Instrument,
  type Page,
  type User,
} from "@/lib/types";

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

function InstrumentsSection({ instruments }: { instruments: Async<number> }) {
  if (instruments.status === "loading") {
    return <p className="text-sm text-muted-foreground">Loading instruments…</p>;
  }
  if (instruments.status === "error") {
    return <RetryError message="Couldn't load instruments." onRetry={instruments.retry} />;
  }
  const total = instruments.data ?? 0;
  return (
    <div className="flex flex-wrap items-center justify-between gap-3">
      <span className="text-sm">
        {total} registered instrument{total === 1 ? "" : "s"}
      </span>
      <div className="flex gap-2">
        <Link href="/instruments" className={buttonVariants({ variant: "outline", size: "sm" })}>
          View all
        </Link>
        <Link href="/instruments/new" className={buttonVariants({ size: "sm" })}>
          Register instrument
        </Link>
      </div>
    </div>
  );
}

type EmptyState = { message: string; cta?: { href: string; label: string } };

// Total and per-status counts come from GET /applications/stats (server-side aggregate),
// never from items.length: those numbers must stay correct no matter how many applications exist.
function ApplicationsSummary({
  stats,
  meta,
  empty,
}: {
  stats: Async<ApplicationStats>;
  meta: ApplicationMeta | null;
  empty: EmptyState;
}) {
  if (stats.status === "loading") {
    return <p className="text-sm text-muted-foreground">Loading applications…</p>;
  }
  if (stats.status === "error") {
    return <RetryError message="Couldn't load applications." onRetry={stats.retry} />;
  }

  const { total, by_status } = stats.data ?? { total: 0, by_status: {} };
  if (total === 0) {
    return (
      <div className="flex flex-wrap items-center justify-between gap-3">
        <span className="text-sm text-muted-foreground">{empty.message}</span>
        {empty.cta ? (
          <Link
            href={empty.cta.href}
            className={buttonVariants({ variant: "outline", size: "sm" })}
          >
            {empty.cta.label}
          </Link>
        ) : null}
      </div>
    );
  }

  return (
    <div className="grid gap-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <span className="text-sm">
          {total} application{total === 1 ? "" : "s"}
        </span>
        <Link href="/applications" className={buttonVariants({ variant: "outline", size: "sm" })}>
          View all
        </Link>
      </div>
      <div className="flex flex-wrap gap-2">
        {/* meta.statuses is already served in lifecycle order (DRAFT ... CERTIFICATE_ISSUED) */}
        {(meta?.statuses ?? [])
          .filter((s) => by_status[s.value])
          .map((s) => (
            <Link
              key={s.value}
              href={`/applications?status=${s.value}`}
              className="inline-flex min-h-11 items-center"
            >
              <Badge variant="secondary">
                {by_status[s.value]} {s.label}
              </Badge>
            </Link>
          ))}
      </div>
    </div>
  );
}

type AttentionRule = { status: string; hint: string; data: Async<Page<Application>> };

// One "Needs your attention" panel backed by several independent queries (one per rule) — each
// rule keeps its own loading/error/retry, per spec 04 §4, but they render as a single list.
function NeedsAttentionSection({ rules }: { rules: AttentionRule[] }) {
  const errored = rules.filter((r) => r.data.status === "error");
  const rows = rules.flatMap((r) =>
    r.data.status === "ready"
      ? (r.data.data?.items ?? []).map((a) => ({
          id: a.id,
          number: a.application_number,
          uid: a.instrument.instrument_uid,
          hint: r.hint,
        }))
      : [],
  );
  const more = rules
    .filter((r) => r.data.status === "ready" && r.data.data && r.data.data.total > r.data.data.items.length)
    .map((r) => ({
      status: r.status,
      count: (r.data.data?.total ?? 0) - (r.data.data?.items.length ?? 0),
    }));

  if (rows.length === 0 && errored.length === 0) return null;
  return (
    <div className="grid gap-2 rounded-lg border border-dashed p-4">
      <p className="text-sm font-medium">Needs your attention</p>
      {errored.map((r) => (
        <RetryError
          key={r.status}
          message={`Couldn't load "${r.hint}" items.`}
          onRetry={r.data.retry}
        />
      ))}
      {rows.length > 0 ? (
        <ul className="grid gap-1">
          {rows.map((row) => (
            <li key={row.id} className="flex flex-wrap items-center justify-between gap-2 text-sm">
              <Link href={`/applications/${row.id}`} className="underline">
                {row.number} · {row.uid}
              </Link>
              <span className="text-muted-foreground">{row.hint}</span>
            </li>
          ))}
        </ul>
      ) : null}
      {more.map((m) => (
        <Link key={m.status} href={`/applications?status=${m.status}`} className="text-sm underline">
          + {m.count} more
        </Link>
      ))}
    </div>
  );
}

function UpcomingInspectionsSection({ upcoming }: { upcoming: Async<Page<Application>> }) {
  if (upcoming.status === "loading") return null; // avoids a flash before the other sections settle
  if (upcoming.status === "error") {
    return <RetryError message="Couldn't load upcoming inspections." onRetry={upcoming.retry} />;
  }
  const items = upcoming.data?.items ?? [];
  if (items.length === 0) return null;
  return (
    <div className="grid gap-2">
      <p className="text-sm font-medium">Upcoming inspections</p>
      <ul className="grid gap-2">
        {items.map((a) => (
          <li key={a.id}>
            <Link
              href={`/applications/${a.id}`}
              className="flex items-center justify-between gap-2 rounded-lg border px-3 py-2 text-sm"
            >
              <span className="font-medium">
                {a.scheduled_date ? new Date(a.scheduled_date).toLocaleDateString() : "—"}
              </span>
              <span>
                <span className="font-mono text-xs text-muted-foreground">
                  {a.application_number}
                </span>
                <span className="ml-2">{a.instrument.instrument_uid}</span>
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}

function RecentSection({
  recent,
  meta,
}: {
  recent: Async<Page<Application>>;
  meta: ApplicationMeta | null;
}) {
  if (recent.status === "loading") {
    return <p className="text-sm text-muted-foreground">Loading recent activity…</p>;
  }
  if (recent.status === "error") {
    return <RetryError message="Couldn't load recent activity." onRetry={recent.retry} />;
  }
  const items = recent.data?.items ?? [];
  if (items.length === 0) return null; // covered by ApplicationsSummary's empty state
  return (
    <div className="grid gap-2">
      <p className="text-sm font-medium">Recent</p>
      <ul className="grid gap-2">
        {items.map((a) => (
          <li key={a.id}>
            <Link
              href={`/applications/${a.id}`}
              className="flex items-center justify-between gap-2 rounded-lg border px-3 py-2 text-sm"
            >
              <span>
                <span className="font-mono text-xs text-muted-foreground">
                  {a.application_number}
                </span>
                <span className="ml-2">{a.instrument.instrument_uid}</span>
              </span>
              <span className="flex items-center gap-2">
                {a.scheduled_date ? (
                  <span className="text-xs text-muted-foreground">
                    Scheduled: {new Date(a.scheduled_date).toLocaleDateString()}
                  </span>
                ) : null}
                <StatusBadge status={a.status} label={labelFor(meta?.statuses, a.status)} />
              </span>
            </Link>
          </li>
        ))}
      </ul>
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

function BusinessDashboard({ user }: { user: User }) {
  const instruments = useAsync(() =>
    api<Page<Instrument>>("/instruments?page_size=1").then((p) => p.total),
  );
  const stats = useAsync(() => getApplicationStats());
  const drafts = useAsync(() => api<Page<Application>>("/applications?status=DRAFT&page_size=5"));
  const recent = useAsync(() => api<Page<Application>>("/applications?page_size=5"));
  const meta = useApplicationMeta();

  const noInstruments = instruments.status === "ready" && instruments.data === 0;
  const empty: EmptyState = noInstruments
    ? {
        message: "Register your first instrument to get started",
        cta: { href: "/instruments/new", label: "Register instrument" },
      }
    : {
        message: "Start a verification application",
        cta: { href: "/applications/new", label: "New application" },
      };

  return (
    <Card>
      <CardHeader>
        <CardTitle>{user.organization_name}</CardTitle>
        <CardDescription>Business dashboard</CardDescription>
      </CardHeader>
      <CardContent className="grid gap-6">
        <InstrumentsSection instruments={instruments} />
        <ApplicationsSummary stats={stats} meta={meta} empty={empty} />
        <NeedsAttentionSection
          rules={[{ status: "DRAFT", hint: "Upload documents & submit", data: drafts }]}
        />
        <RecentSection recent={recent} meta={meta} />
      </CardContent>
    </Card>
  );
}

// Spec 19 §6.1: the one new KPI this spec adds to the officer dashboard — reuses
// GET /admin/certificates/stats, now admitted for LM_OFFICER (spec 19 §4), already scoped to
// the officer's own district via scope_certificates -> scope_applications.
function ExpiringCertsSection({ stats }: { stats: Async<AdminCertificateStats> }) {
  if (stats.status === "loading") return null;
  if (stats.status === "error") {
    return <RetryError message="Couldn't load certificate stats." onRetry={stats.retry} />;
  }
  const count = stats.data?.expiring_soon ?? 0;
  return (
    <Link
      href="/certificates/expiring-soon"
      className="flex items-center justify-between gap-2 rounded-lg border px-3 py-2 text-sm"
    >
      <span>Certificates expiring soon</span>
      <Badge variant="secondary">{count}</Badge>
    </Link>
  );
}

function OfficerDashboard({ user }: { user: User }) {
  const instruments = useAsync(() =>
    api<Page<Instrument>>("/instruments?page_size=1").then((p) => p.total),
  );
  const stats = useAsync(() => getApplicationStats());
  const certStats = useAsync(() => getAdminCertificateStats());
  const submitted = useAsync(() =>
    api<Page<Application>>("/applications?status=SUBMITTED&page_size=5"),
  );
  const inReview = useAsync(() =>
    api<Page<Application>>("/applications?status=DOCUMENT_REVIEW&page_size=5"),
  );
  const upcoming = useAsync(() =>
    api<Page<Application>>("/applications?status=SCHEDULED&sort=scheduled_asc&page_size=5"),
  );
  // Also this step 6's "my inspections": reuses spec 05's sort, no new endpoint needed.
  const inspecting = useAsync(() =>
    api<Page<Application>>("/applications?status=INSPECTION&sort=scheduled_asc&page_size=5"),
  );
  const recent = useAsync(() => api<Page<Application>>("/applications?page_size=5"));
  const meta = useApplicationMeta();

  return (
    <Card>
      <CardHeader>
        <CardTitle>Officer dashboard</CardTitle>
        <CardDescription>
          Jurisdiction: {user.state_code} / {user.district_code}
        </CardDescription>
      </CardHeader>
      <CardContent className="grid gap-6">
        <InstrumentsSection instruments={instruments} />
        <ApplicationsSummary
          stats={stats}
          meta={meta}
          empty={{ message: "No applications in your district yet" }}
        />
        <ExpiringCertsSection stats={certStats} />
        <NeedsAttentionSection
          rules={[
            { status: "SUBMITTED", hint: "Start document review", data: submitted },
            { status: "DOCUMENT_REVIEW", hint: "Schedule inspection", data: inReview },
            { status: "INSPECTION", hint: "Continue inspection", data: inspecting },
          ]}
        />
        <UpcomingInspectionsSection upcoming={upcoming} />
        <RecentSection recent={recent} meta={meta} />
      </CardContent>
    </Card>
  );
}

function JurisdictionLink() {
  return (
    <div className="flex flex-wrap gap-2">
      <Link href="/instruments" className={buttonVariants({ variant: "outline", size: "sm" })}>
        View instruments
      </Link>
      <Link href="/applications" className={buttonVariants({ variant: "outline", size: "sm" })}>
        View applications
      </Link>
    </div>
  );
}

// Spec 20 §6.1: replaces the old static "Assigned verifications will appear here" stub. Reuses
// GET /applications/stats (now GATC-admitted) and the same ApplicationsSummary/
// NeedsAttentionSection/RecentSection components OfficerDashboard already uses -- only two
// needs-attention buckets (not three): GATC is never in SUBMITTED/DOCUMENT_REVIEW, structurally
// not its job (spec 20 §2). No instrument count section either (GATC has no instrument access).
function GatcDashboard({ user }: { user: User }) {
  const stats = useAsync(() => getApplicationStats());
  const scheduled = useAsync(() =>
    api<Page<Application>>("/applications?status=SCHEDULED&sort=scheduled_asc&page_size=5"),
  );
  const inspecting = useAsync(() =>
    api<Page<Application>>("/applications?status=INSPECTION&sort=scheduled_asc&page_size=5"),
  );
  const recent = useAsync(() => api<Page<Application>>("/applications?page_size=5"));
  const meta = useApplicationMeta();

  return (
    <Card>
      <CardHeader>
        <CardTitle>GATC dashboard</CardTitle>
        <CardDescription>{user.organization_name}</CardDescription>
      </CardHeader>
      <CardContent className="grid gap-6">
        <ApplicationsSummary
          stats={stats}
          meta={meta}
          empty={{ message: "No applications assigned yet" }}
        />
        <NeedsAttentionSection
          rules={[
            { status: "SCHEDULED", hint: "Start verification", data: scheduled },
            { status: "INSPECTION", hint: "Continue inspection", data: inspecting },
          ]}
        />
        <RecentSection recent={recent} meta={meta} />
      </CardContent>
    </Card>
  );
}

function RoleCard({ user }: { user: User }) {
  if (user.role === "BUSINESS") {
    return <BusinessDashboard user={user} />;
  }
  if (user.role === "LM_OFFICER") {
    return <OfficerDashboard user={user} />;
  }
  if (user.role === "GATC") {
    return <GatcDashboard user={user} />;
  }
  if (ADMIN_ROLES.includes(user.role)) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Admin dashboard</CardTitle>
          <CardDescription>
            Scope: {user.state_code ?? "All states"}
            {user.district_code ? ` / ${user.district_code}` : ""}
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-3">
          <div className="flex flex-wrap gap-2">
            <Link href="/admin" className={buttonVariants({ variant: "outline", size: "sm" })}>
              Expiry dashboard
            </Link>
          </div>
          <div>
            <JurisdictionLink />
          </div>
        </CardContent>
      </Card>
    );
  }
  // Unreachable: SUPER_ADMIN/STATE_ADMIN/DISTRICT_ADMIN/LM_OFFICER/GATC/BUSINESS are all handled
  // explicitly above. Kept as a safety net, not a real fallback.
  return null;
}

export default function DashboardPage() {
  const { user } = useAuth();
  if (!user) return null;
  return (
    <div className="grid gap-6">
      <h1 className="text-2xl font-semibold">
        Welcome, {user.full_name}{" "}
        <span className="text-base font-normal text-muted-foreground">({user.role})</span>
      </h1>
      <RoleCard user={user} />
    </div>
  );
}
