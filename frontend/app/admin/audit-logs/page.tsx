"use client";

import { useEffect, useState } from "react";

import { NO_ACCESS, StateMessage } from "@/components/instruments/state-message";
import { buttonVariants } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { ApiError, getAuditLogs } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { AuditLogEntry, Page } from "@/lib/types";

const PAGE_SIZE = 20;

type State =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "ready"; data: Page<AuditLogEntry> };

// Spec 17 §6.7: timestamp / actor / action / entity, filterable, with a details JSON viewer per
// row via Dialog (no collapsible primitive exists in this codebase, so a modal is the simplest
// fit — spec 17 §5.8).
function AuditLogsList() {
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [action, setAction] = useState("");
  const [entityType, setEntityType] = useState("");
  const [debouncedAction, setDebouncedAction] = useState("");
  const [debouncedEntityType, setDebouncedEntityType] = useState("");
  const [page, setPage] = useState(1);
  const [state, setState] = useState<State>({ kind: "loading" });
  const [detailsRow, setDetailsRow] = useState<AuditLogEntry | null>(null);

  useEffect(() => {
    const t = setTimeout(() => {
      setDebouncedAction(action.trim());
      setDebouncedEntityType(entityType.trim());
      setPage(1);
    }, 300);
    return () => clearTimeout(t);
  }, [action, entityType]);

  useEffect(() => {
    let cancelled = false;
    const params = new URLSearchParams({ page: String(page), page_size: String(PAGE_SIZE) });
    if (dateFrom) params.set("date_from", dateFrom);
    if (dateTo) params.set("date_to", dateTo);
    if (debouncedAction) params.set("action", debouncedAction);
    if (debouncedEntityType) params.set("entity_type", debouncedEntityType);
    getAuditLogs(params).then(
      (data) => !cancelled && setState({ kind: "ready", data }),
      (err: unknown) => {
        if (cancelled) return;
        const message =
          err instanceof ApiError && err.status === 403
            ? "You don't have access to the audit log."
            : "Could not load the audit log.";
        setState({ kind: "error", message });
      },
    );
    return () => {
      cancelled = true;
    };
  }, [dateFrom, dateTo, debouncedAction, debouncedEntityType, page]);

  const data = state.kind === "ready" ? state.data : null;
  const lastPage = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1;

  return (
    <div className="grid gap-6">
      <div>
        <h1 className="text-2xl font-semibold">Audit logs</h1>
        <p className="text-sm text-muted-foreground">Every significant action in the system.</p>
      </div>

      <div className="grid gap-3 sm:grid-cols-4">
        <div className="grid gap-1.5">
          <Label htmlFor="date_from">From</Label>
          <Input
            id="date_from"
            type="date"
            className="h-10"
            value={dateFrom}
            onChange={(e) => {
              setDateFrom(e.target.value);
              setPage(1);
            }}
          />
        </div>
        <div className="grid gap-1.5">
          <Label htmlFor="date_to">To</Label>
          <Input
            id="date_to"
            type="date"
            className="h-10"
            value={dateTo}
            onChange={(e) => {
              setDateTo(e.target.value);
              setPage(1);
            }}
          />
        </div>
        <div className="grid gap-1.5">
          <Label htmlFor="action">Action</Label>
          <Input
            id="action"
            placeholder="e.g. USER_CREATED"
            className="h-10"
            value={action}
            onChange={(e) => setAction(e.target.value)}
          />
        </div>
        <div className="grid gap-1.5">
          <Label htmlFor="entity_type">Entity type</Label>
          <Input
            id="entity_type"
            placeholder="e.g. user"
            className="h-10"
            value={entityType}
            onChange={(e) => setEntityType(e.target.value)}
          />
        </div>
      </div>

      {state.kind === "loading" ? (
        <p className="text-sm text-muted-foreground">Loading…</p>
      ) : state.kind === "error" ? (
        <StateMessage title={state.message} />
      ) : data && data.items.length === 0 ? (
        <StateMessage title="No matching activity." />
      ) : data ? (
        <>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Timestamp</TableHead>
                <TableHead>Actor</TableHead>
                <TableHead>Action</TableHead>
                <TableHead>Entity</TableHead>
                <TableHead />
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.items.map((row) => (
                <TableRow key={row.id}>
                  <TableCell className="text-sm">
                    {new Date(row.created_at).toLocaleString()}
                  </TableCell>
                  <TableCell>{row.actor_name ?? "System"}</TableCell>
                  <TableCell className="font-mono text-xs">{row.action}</TableCell>
                  <TableCell className="text-sm">
                    {row.entity_type ?? "—"}
                    {row.entity_id ? (
                      <>
                        <br />
                        <span className="font-mono text-xs text-muted-foreground">
                          {row.entity_id}
                        </span>
                      </>
                    ) : null}
                  </TableCell>
                  <TableCell className="text-right">
                    <button
                      type="button"
                      className={buttonVariants({ variant: "outline", size: "sm" })}
                      onClick={() => setDetailsRow(row)}
                    >
                      View details
                    </button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>

          <div className="flex items-center justify-between text-sm text-muted-foreground">
            <span>
              {data.total} event{data.total === 1 ? "" : "s"}
            </span>
            {lastPage > 1 ? (
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  className={buttonVariants({ variant: "outline", size: "sm" })}
                  disabled={page <= 1}
                  onClick={() => setPage((p) => p - 1)}
                >
                  Previous
                </button>
                <span>
                  Page {page} of {lastPage}
                </span>
                <button
                  type="button"
                  className={buttonVariants({ variant: "outline", size: "sm" })}
                  disabled={page >= lastPage}
                  onClick={() => setPage((p) => p + 1)}
                >
                  Next
                </button>
              </div>
            ) : null}
          </div>
        </>
      ) : null}

      <Dialog open={detailsRow !== null} onOpenChange={(open) => !open && setDetailsRow(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{detailsRow?.action}</DialogTitle>
          </DialogHeader>
          <pre className="max-h-80 overflow-auto rounded-md bg-muted p-3 text-xs">
            {detailsRow ? JSON.stringify(detailsRow.details, null, 2) : ""}
          </pre>
        </DialogContent>
      </Dialog>
    </div>
  );
}

export default function AuditLogsPage() {
  const { user } = useAuth();
  if (!user || !["SUPER_ADMIN", "STATE_ADMIN"].includes(user.role)) {
    return <StateMessage title={NO_ACCESS} />;
  }
  return <AuditLogsList />;
}
