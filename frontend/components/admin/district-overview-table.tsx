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
import { getDistrictOverview } from "@/lib/api";
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

// Spec 18 §4: the district-level sibling of StateOverviewTable — one row per district of the
// State Admin's own state (the backend forces this regardless of any state_code param), always
// present. Bounded to one state's district count, never paginated.
export function DistrictOverviewTable() {
  const overview = useAsync(() => getDistrictOverview());

  if (overview.status === "loading") {
    return <p className="text-sm text-muted-foreground">Loading district overview…</p>;
  }
  if (overview.status === "error") {
    return <RetryError message="Couldn't load the district overview." onRetry={overview.retry} />;
  }
  const rows = overview.data ?? [];

  return (
    <div className="max-h-96 overflow-y-auto rounded-md border">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>District</TableHead>
            <TableHead className="text-right">Instruments</TableHead>
            <TableHead className="text-right">Pending apps</TableHead>
            <TableHead className="text-right">Certs valid</TableHead>
            <TableHead className="text-right">Certs expired</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((r) => (
            <TableRow key={r.district_code}>
              <TableCell>{r.district_name}</TableCell>
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
