"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { NO_ACCESS, StateMessage } from "@/components/instruments/state-message";
import { SelectField } from "@/components/select-field";
import { Badge } from "@/components/ui/badge";
import { buttonVariants } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { ApiError, getCertificates } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { Certificate, Page } from "@/lib/types";

const PAGE_SIZE = 20;
const ALL = "__all__";
const STATUSES = ["VALID", "EXPIRED", "REVOKED", "SUPERSEDED"];

type State =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "ready"; data: Page<Certificate> };

// Spec 17 §1.6/§6.3: no certificate list existed before this step (only get-by-id/pdf and the
// admin expiring-soon slice) — this is the general directory, reusing GET /api/certificates.
function CertificatesList() {
  const [status, setStatus] = useState(ALL);
  const [page, setPage] = useState(1);
  const [state, setState] = useState<State>({ kind: "loading" });

  useEffect(() => {
    let cancelled = false;
    const params = new URLSearchParams({ page: String(page), page_size: String(PAGE_SIZE) });
    if (status !== ALL) params.set("status", status);
    getCertificates(params).then(
      (data) => !cancelled && setState({ kind: "ready", data }),
      (err: unknown) => {
        if (cancelled) return;
        const message =
          err instanceof ApiError && err.status === 403
            ? "You don't have access to certificates."
            : "Could not load certificates.";
        setState({ kind: "error", message });
      },
    );
    return () => {
      cancelled = true;
    };
  }, [status, page]);

  const data = state.kind === "ready" ? state.data : null;
  const lastPage = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1;
  const statusOptions = [
    { value: ALL, label: "All statuses" },
    ...STATUSES.map((s) => ({ value: s, label: s })),
  ];

  return (
    <div className="grid gap-6">
      <div>
        <h1 className="text-2xl font-semibold">Certificates</h1>
        <p className="text-sm text-muted-foreground">Every issued certificate, across every state.</p>
      </div>

      <div className="max-w-xs">
        <SelectField
          name="status_filter"
          label="Status"
          value={status}
          options={statusOptions}
          onChange={(v) => {
            setStatus(v || ALL);
            setPage(1);
          }}
        />
      </div>

      {state.kind === "loading" ? (
        <p className="text-sm text-muted-foreground">Loading certificates…</p>
      ) : state.kind === "error" ? (
        <StateMessage title={state.message} />
      ) : data && data.items.length === 0 ? (
        <StateMessage title="No certificates match." />
      ) : data ? (
        <>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Certificate</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Instrument</TableHead>
                <TableHead>Business</TableHead>
                <TableHead>Valid until</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.items.map((c) => (
                <TableRow key={c.id}>
                  <TableCell>
                    <Link href={`/certificates/${c.id}`} className="font-mono text-xs underline">
                      {c.certificate_number}
                    </Link>
                  </TableCell>
                  <TableCell>
                    <Badge variant="secondary">{c.status}</Badge>
                  </TableCell>
                  <TableCell className="text-sm">
                    <span className="font-mono text-xs">{c.instrument_uid}</span>
                    <br />
                    {c.manufacturer} {c.model}
                  </TableCell>
                  <TableCell>{c.organization_name}</TableCell>
                  <TableCell>{new Date(c.valid_until).toLocaleDateString()}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>

          <div className="flex items-center justify-between text-sm text-muted-foreground">
            <span>
              {data.total} certificate{data.total === 1 ? "" : "s"}
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
    </div>
  );
}

export default function AdminCertificatesPage() {
  const { user } = useAuth();
  if (!user || user.role !== "SUPER_ADMIN") return <StateMessage title={NO_ACCESS} />;
  return <CertificatesList />;
}
