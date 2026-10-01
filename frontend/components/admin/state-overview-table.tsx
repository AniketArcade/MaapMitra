"use client";

import { buttonVariants } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { getStateOverview } from "@/lib/api";
import { useAsync } from "@/lib/use-async";

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

// Spec 17 §6.4: one row per state/UT, always present — the Phase 1 substitute for an India map
// (root CLAUDE.md's Deferred list names Leaflet maps explicitly). Bounded to ~36 rows, never
// paginated.
export function StateOverviewTable() {
  const overview = useAsync(() => getStateOverview());

  if (overview.status === "loading") {
    return <p className="text-sm text-muted-foreground">Loading state overview…</p>;
  }
  if (overview.status === "error") {
    return <RetryError message="Couldn't load the state overview." onRetry={overview.retry} />;
  }
  const rows = overview.data ?? [];

  return (
    <div className="max-h-96 overflow-y-auto rounded-md border">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>State</TableHead>
            <TableHead className="text-right">Instruments</TableHead>
            <TableHead className="text-right">Pending apps</TableHead>
            <TableHead className="text-right">Certs valid</TableHead>
            <TableHead className="text-right">Certs expired</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((r) => (
            <TableRow key={r.state_code}>
              <TableCell>{r.state_name}</TableCell>
              <TableCell className="text-right">{r.instrument_count}</TableCell>
              <TableCell className="text-right">{r.pending_applications}</TableCell>
              <TableCell className="text-right">{r.certs_valid}</TableCell>
              <TableCell className="text-right">{r.certs_expired}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
