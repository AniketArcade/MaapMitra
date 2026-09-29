"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useState } from "react";

import { StatusBadge } from "@/components/applications/status-badge";
import { StateMessage } from "@/components/instruments/state-message";
import { SelectField } from "@/components/select-field";
import { buttonVariants } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { ApiError, api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { getApplicationMeta, labelFor } from "@/lib/meta";
import type { Application, ApplicationMeta, Page } from "@/lib/types";

const PAGE_SIZE = 20;
const ALL = "__all__";

type State =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "ready"; data: Page<Application> };

function ApplicationsList() {
  const { user } = useAuth();
  const isBusiness = user?.role === "BUSINESS";
  const router = useRouter();
  const searchParams = useSearchParams();
  const [meta, setMeta] = useState<ApplicationMeta | null>(null);
  const [query, setQuery] = useState("");
  const [debounced, setDebounced] = useState("");
  const [page, setPage] = useState(1);
  const [state, setState] = useState<State>({ kind: "loading" });

  useEffect(() => {
    getApplicationMeta().then(setMeta, () => undefined);
  }, []);

  // Derived from the URL every render (not just a useState initializer) so a link elsewhere
  // that changes ?status= while this page is already mounted (e.g. Back/Forward) takes effect.
  // Until meta has loaded there's nothing to validate an unknown value against, so it's
  // treated as "no filter" rather than sent straight to the backend (which would 422 on it).
  const knownStatuses = useMemo(
    () => new Set((meta?.statuses ?? []).map((s) => s.value)),
    [meta],
  );
  const rawStatus = searchParams.get("status");
  const status = rawStatus && knownStatuses.has(rawStatus) ? rawStatus : ALL;

  function setStatus(value: string): void {
    const qs = value && value !== ALL ? `?status=${encodeURIComponent(value)}` : "";
    router.replace(`/applications${qs}`);
    setPage(1);
  }

  useEffect(() => {
    const t = setTimeout(() => {
      setDebounced(query.trim());
      setPage(1);
    }, 300);
    return () => clearTimeout(t);
  }, [query]);

  useEffect(() => {
    let cancelled = false;
    const params = new URLSearchParams({ page: String(page), page_size: String(PAGE_SIZE) });
    if (debounced) params.set("q", debounced);
    if (status !== ALL) params.set("status", status);
    api<Page<Application>>(`/applications?${params}`).then(
      (data) => !cancelled && setState({ kind: "ready", data }),
      (err: unknown) => {
        if (cancelled) return;
        const message =
          err instanceof ApiError && err.status === 403
            ? "You don't have access to applications."
            : "Could not load applications.";
        setState({ kind: "error", message });
      },
    );
    return () => {
      cancelled = true;
    };
  }, [debounced, status, page]);

  const data = state.kind === "ready" ? state.data : null;
  const lastPage = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1;
  const statusOptions = [
    { value: ALL, label: "All statuses" },
    ...(meta?.statuses ?? [])
      .filter((s) => isBusiness || s.value !== "DRAFT") // officials never see drafts
      .map((s) => ({ value: s.value, label: s.label })),
  ];

  return (
    <div className="grid gap-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">Applications</h1>
          {!isBusiness ? (
            <p className="text-sm text-muted-foreground">Submitted applications in your jurisdiction.</p>
          ) : null}
        </div>
        {isBusiness ? (
          <Link href="/applications/new" className={buttonVariants()}>
            New application
          </Link>
        ) : null}
      </div>

      <div className="grid gap-3 sm:grid-cols-[1fr_14rem]">
        <Input
          type="search"
          placeholder="Search by application number, instrument UID or serial"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          maxLength={100}
          className="h-10"
          aria-label="Search applications"
        />
        <SelectField
          name="status_filter"
          label="Status"
          value={status}
          options={statusOptions}
          onChange={(v) => setStatus(v || ALL)}
        />
      </div>

      {state.kind === "loading" ? (
        <p className="text-sm text-muted-foreground">Loading applications…</p>
      ) : state.kind === "error" ? (
        <StateMessage title={state.message} />
      ) : data && data.items.length === 0 ? (
        <StateMessage
          title={debounced || status !== ALL ? "No applications match." : "No applications yet"}
        >
          {isBusiness && !debounced && status === ALL ? (
            <Link href="/applications/new" className="underline">
              Apply for verification
            </Link>
          ) : null}
        </StateMessage>
      ) : data ? (
        <>
          <ul className="grid gap-3 md:hidden">
            {data.items.map((a) => (
              <li key={a.id}>
                <Link href={`/applications/${a.id}`} className="grid gap-1 rounded-lg border p-4">
                  <span className="flex items-center justify-between gap-2">
                    <span className="font-mono text-xs text-muted-foreground">{a.application_number}</span>
                    <StatusBadge status={a.status} label={labelFor(meta?.statuses, a.status)} />
                  </span>
                  <span className="font-medium">
                    {a.instrument.instrument_uid} · S/N {a.instrument.serial_number}
                  </span>
                  <span className="text-sm text-muted-foreground">
                    {labelFor(meta?.application_types, a.application_type)}
                    {!isBusiness ? ` · ${a.organization_name}` : ""}
                  </span>
                </Link>
              </li>
            ))}
          </ul>

          <div className="hidden md:block">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Application</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Instrument</TableHead>
                  <TableHead>Type</TableHead>
                  {!isBusiness ? <TableHead>Business</TableHead> : null}
                  <TableHead>Submitted</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.items.map((a) => (
                  <TableRow key={a.id}>
                    <TableCell>
                      <Link href={`/applications/${a.id}`} className="font-mono text-xs underline">
                        {a.application_number}
                      </Link>
                    </TableCell>
                    <TableCell>
                      <StatusBadge status={a.status} label={labelFor(meta?.statuses, a.status)} />
                    </TableCell>
                    <TableCell className="text-sm">
                      <span className="font-mono text-xs">{a.instrument.instrument_uid}</span>
                      <br />
                      S/N {a.instrument.serial_number}
                    </TableCell>
                    <TableCell>{labelFor(meta?.application_types, a.application_type)}</TableCell>
                    {!isBusiness ? <TableCell>{a.organization_name}</TableCell> : null}
                    <TableCell className="text-sm">
                      {a.submitted_at ? new Date(a.submitted_at).toLocaleDateString() : "—"}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>

          <div className="flex items-center justify-between text-sm text-muted-foreground">
            <span>
              {data.total} application{data.total === 1 ? "" : "s"}
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

export default function ApplicationsPage() {
  return (
    <Suspense>
      <ApplicationsList />
    </Suspense>
  );
}
