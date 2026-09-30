"use client";

import { NO_ACCESS, StateMessage } from "@/components/instruments/state-message";
import { buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { api, getAdminCertificateStats } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { ADMIN_ROLES, type AdminCertificateStats, type Certificate, type Page } from "@/lib/types";
import { type Async, useAsync } from "@/lib/use-async";

const PAGE_SIZE = 20;

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

function daysRemaining(validUntil: string): number {
  const ms = new Date(validUntil).getTime() - Date.now();
  return Math.ceil(ms / (1000 * 60 * 60 * 24));
}

function StatsCards({ stats }: { stats: Async<AdminCertificateStats> }) {
  if (stats.status === "loading") {
    return <p className="text-sm text-muted-foreground">Loading counts…</p>;
  }
  if (stats.status === "error") {
    return <RetryError message="Couldn't load certificate counts." onRetry={stats.retry} />;
  }
  const s = stats.data ?? { valid: 0, expiring_soon: 0, expired: 0, revoked: 0 };
  const cards = [
    { label: "Valid", value: s.valid },
    { label: "Expiring soon", value: s.expiring_soon },
    { label: "Expired", value: s.expired },
    { label: "Revoked", value: s.revoked },
  ];
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
      {cards.map((c) => (
        <Card key={c.label}>
          <CardHeader>
            <CardTitle className="text-2xl">{c.value}</CardTitle>
          </CardHeader>
          <CardContent className="text-sm text-muted-foreground">{c.label}</CardContent>
        </Card>
      ))}
    </div>
  );
}

function ExpiringSoonTable({ list }: { list: Async<Page<Certificate>> }) {
  if (list.status === "loading") {
    return <p className="text-sm text-muted-foreground">Loading…</p>;
  }
  if (list.status === "error") {
    return <RetryError message="Couldn't load expiring certificates." onRetry={list.retry} />;
  }
  const items = list.data?.items ?? [];
  if (items.length === 0) {
    return <StateMessage title="Nothing expiring soon" />;
  }
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Certificate</TableHead>
          <TableHead>Business</TableHead>
          <TableHead>Instrument</TableHead>
          <TableHead>Valid until</TableHead>
          <TableHead>Days left</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {items.map((c) => (
          <TableRow key={c.id}>
            <TableCell className="font-mono text-xs">{c.certificate_number}</TableCell>
            <TableCell>{c.organization_name}</TableCell>
            <TableCell>
              {c.manufacturer} {c.model}
            </TableCell>
            <TableCell>{new Date(c.valid_until).toLocaleDateString()}</TableCell>
            <TableCell>{daysRemaining(c.valid_until)}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}

export default function AdminPage() {
  const { user } = useAuth();
  const stats = useAsync(() => getAdminCertificateStats());
  const list = useAsync(() =>
    api<Page<Certificate>>(`/admin/certificates/expiring-soon?page_size=${PAGE_SIZE}`),
  );

  if (!user || !ADMIN_ROLES.includes(user.role)) return <StateMessage title={NO_ACCESS} />;

  return (
    <div className="grid gap-6">
      <h1 className="text-2xl font-semibold">Expiry dashboard</h1>
      <StatsCards stats={stats} />
      <div className="grid gap-3">
        <h2 className="text-lg font-medium">Expiring soon</h2>
        <ExpiringSoonTable list={list} />
      </div>
    </div>
  );
}
