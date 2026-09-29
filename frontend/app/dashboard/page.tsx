"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { StatusBadge } from "@/components/applications/status-badge";
import { Badge } from "@/components/ui/badge";
import { buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { api, getApplicationStats } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { getApplicationMeta, labelFor } from "@/lib/meta";
import { type Async, useAsync } from "@/lib/use-async";
import {
  ADMIN_ROLES,
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

// Total and per-status counts come from GET /applications/stats (server-side aggregate),
// never from items.length: those numbers must stay correct no matter how many applications exist.
function ApplicationsSummary({
  stats,
  meta,
  instrumentTotal,
}: {
  stats: Async<ApplicationStats>;
  meta: ApplicationMeta | null;
  instrumentTotal: number | null;
}) {
  if (stats.status === "loading") {
    return <p className="text-sm text-muted-foreground">Loading applications…</p>;
  }
  if (stats.status === "error") {
    return <RetryError message="Couldn't load applications." onRetry={stats.retry} />;
  }

  const { total, by_status } = stats.data ?? { total: 0, by_status: {} };
  if (total === 0) {
    const noInstruments = instrumentTotal === 0;
    return (
      <div className="flex flex-wrap items-center justify-between gap-3">
        <span className="text-sm text-muted-foreground">
          {noInstruments
            ? "Register your first instrument to get started"
            : "Start a verification application"}
        </span>
        <Link
          href={noInstruments ? "/instruments/new" : "/applications/new"}
          className={buttonVariants({ variant: "outline", size: "sm" })}
        >
          {noInstruments ? "Register instrument" : "New application"}
        </Link>
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

function NeedsAttentionSection({ drafts }: { drafts: Async<Page<Application>> }) {
  if (drafts.status === "loading") return null; // avoids a flash before the other sections settle
  if (drafts.status === "error") {
    return <RetryError message="Couldn't load items needing attention." onRetry={drafts.retry} />;
  }
  const { items, total } = drafts.data ?? { items: [], total: 0, page: 1, page_size: 5 };
  if (total === 0) return null;
  return (
    <div className="grid gap-2 rounded-lg border border-dashed p-4">
      <p className="text-sm font-medium">Needs your attention</p>
      <ul className="grid gap-1">
        {items.map((a) => (
          <li key={a.id} className="flex flex-wrap items-center justify-between gap-2 text-sm">
            <Link href={`/applications/${a.id}`} className="underline">
              {a.application_number} · {a.instrument.instrument_uid}
            </Link>
            <span className="text-muted-foreground">Upload documents &amp; submit</span>
          </li>
        ))}
      </ul>
      {total > items.length ? (
        <Link href="/applications?status=DRAFT" className="text-sm underline">
          + {total - items.length} more
        </Link>
      ) : null}
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
              <StatusBadge status={a.status} label={labelFor(meta?.statuses, a.status)} />
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}

function BusinessDashboard({ user }: { user: User }) {
  const instruments = useAsync(() =>
    api<Page<Instrument>>("/instruments?page_size=1").then((p) => p.total),
  );
  const stats = useAsync(() => getApplicationStats());
  const drafts = useAsync(() => api<Page<Application>>("/applications?status=DRAFT&page_size=5"));
  const recent = useAsync(() => api<Page<Application>>("/applications?page_size=5"));
  const [meta, setMeta] = useState<ApplicationMeta | null>(null);
  useEffect(() => {
    getApplicationMeta().then(setMeta, () => undefined);
  }, []);

  return (
    <Card>
      <CardHeader>
        <CardTitle>{user.organization_name}</CardTitle>
        <CardDescription>Business dashboard</CardDescription>
      </CardHeader>
      <CardContent className="grid gap-6">
        <InstrumentsSection instruments={instruments} />
        <ApplicationsSummary
          stats={stats}
          meta={meta}
          instrumentTotal={instruments.status === "ready" ? instruments.data : null}
        />
        <NeedsAttentionSection drafts={drafts} />
        <RecentSection recent={recent} meta={meta} />
      </CardContent>
    </Card>
  );
}

function useTotal(path: string): number | null {
  const [total, setTotal] = useState<number | null>(null);
  useEffect(() => {
    api<Page<unknown>>(path).then(
      (page) => setTotal(page.total),
      () => setTotal(null),
    );
  }, [path]);
  return total;
}

function ReviewQueue() {
  const total = useTotal("/applications?status=SUBMITTED&page_size=1");
  return (
    <div className="flex flex-wrap items-center justify-between gap-3">
      <span className="text-sm">
        {total === null ? "Submitted, awaiting review" : `${total} submitted, awaiting review`}
      </span>
      <Link href="/applications?status=SUBMITTED" className={buttonVariants({ size: "sm" })}>
        Review queue
      </Link>
    </div>
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

function RoleCard({ user }: { user: User }) {
  if (user.role === "BUSINESS") {
    return <BusinessDashboard user={user} />;
  }
  if (user.role === "LM_OFFICER") {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Officer dashboard</CardTitle>
          <CardDescription>
            Jurisdiction: {user.state_code} / {user.district_code}
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-3">
          <ReviewQueue />
          <p className="text-sm text-muted-foreground">Scheduled inspections will appear here.</p>
          <div>
            <JurisdictionLink />
          </div>
        </CardContent>
      </Card>
    );
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
          <p className="text-sm text-muted-foreground">
            Statistics, users and audit logs will appear here.
          </p>
          <div>
            <JurisdictionLink />
          </div>
        </CardContent>
      </Card>
    );
  }
  return (
    <Card>
      <CardHeader>
        <CardTitle>GATC dashboard</CardTitle>
        <CardDescription>{user.organization_name}</CardDescription>
      </CardHeader>
      <CardContent className="text-sm text-muted-foreground">
        Assigned verifications will appear here.
      </CardContent>
    </Card>
  );
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
