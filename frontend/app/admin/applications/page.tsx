"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useState } from "react";

import { StatusBadge } from "@/components/applications/status-badge";
import { NO_ACCESS, StateMessage } from "@/components/instruments/state-message";
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
import { getApplicationMeta, getInstrumentMeta, labelFor } from "@/lib/meta";
import type { Application, ApplicationMeta, InstrumentMeta, Page } from "@/lib/types";

const PAGE_SIZE = 20;
const ALL = "__all__";

type State =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "ready"; data: Page<Application> };

// Spec 17 §6.2: the same table the business/officer /applications page renders, cloned rather
// than parameterized — this view is unconditionally unfiltered by jurisdiction (SUPER_ADMIN only)
// and adds State/District columns + filters the original page has no use for.
function AdminApplicationsList() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [meta, setMeta] = useState<ApplicationMeta | null>(null);
  const [instrumentMeta, setInstrumentMeta] = useState<InstrumentMeta | null>(null);
  const [query, setQuery] = useState("");
  const [debounced, setDebounced] = useState("");
  const [page, setPage] = useState(1);
  const [state, setState] = useState<State>({ kind: "loading" });

  useEffect(() => {
    getApplicationMeta().then(setMeta, () => undefined);
    getInstrumentMeta().then(setInstrumentMeta, () => undefined);
  }, []);

  const knownStatuses = useMemo(() => new Set((meta?.statuses ?? []).map((s) => s.value)), [meta]);
  const rawStatus = searchParams.get("status");
  const status = rawStatus && knownStatuses.has(rawStatus) ? rawStatus : ALL;

  const knownStates = useMemo(
    () => new Set((instrumentMeta?.regions ?? []).map((r) => r.state_code)),
    [instrumentMeta],
  );
  const rawStateCode = searchParams.get("state_code");
  const stateCode = rawStateCode && knownStates.has(rawStateCode) ? rawStateCode : "";
  const districtsForState = useMemo(
    () => instrumentMeta?.regions.find((r) => r.state_code === stateCode)?.districts ?? [],
    [instrumentMeta, stateCode],
  );
  const knownDistricts = useMemo(
    () => new Set(districtsForState.map((d) => d.code)),
    [districtsForState],
  );
  const rawDistrictCode = searchParams.get("district_code");
  const districtCode =
    rawDistrictCode && knownDistricts.has(rawDistrictCode) ? rawDistrictCode : "";

  function pushFilters(next: { status?: string; state_code?: string; district_code?: string }) {
    const params = new URLSearchParams();
    const merged = { status, state_code: stateCode, district_code: districtCode, ...next };
    if (merged.status && merged.status !== ALL) params.set("status", merged.status);
    if (merged.state_code) params.set("state_code", merged.state_code);
    if (merged.district_code) params.set("district_code", merged.district_code);
    router.replace(`/admin/applications${params.size ? `?${params}` : ""}`);
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
    if (stateCode) params.set("state_code", stateCode);
    if (districtCode) params.set("district_code", districtCode);
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
  }, [debounced, status, stateCode, districtCode, page]);

  const data = state.kind === "ready" ? state.data : null;
  const lastPage = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1;
  const statusOptions = [
    { value: ALL, label: "All statuses" },
    ...(meta?.statuses ?? []).map((s) => ({ value: s.value, label: s.label })),
  ];
  const stateOptions = [
    { value: "", label: "All states" },
    ...(instrumentMeta?.regions ?? []).map((r) => ({ value: r.state_code, label: r.state_name })),
  ];
  const districtOptions = [
    { value: "", label: "All districts" },
    ...districtsForState.map((d) => ({ value: d.code, label: d.name })),
  ];

  return (
    <div className="grid gap-6">
      <div>
        <h1 className="text-2xl font-semibold">Applications</h1>
        <p className="text-sm text-muted-foreground">Every application, across every state.</p>
      </div>

      <div className="grid gap-3 sm:grid-cols-[1fr_12rem_12rem_12rem]">
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
          onChange={(v) => pushFilters({ status: v || ALL })}
        />
        <SelectField
          name="state_filter"
          label="State"
          value={stateCode}
          options={stateOptions}
          onChange={(v) => pushFilters({ state_code: v, district_code: "" })}
        />
        <SelectField
          name="district_filter"
          label="District"
          value={districtCode}
          options={districtOptions}
          onChange={(v) => pushFilters({ district_code: v })}
          disabled={!stateCode}
        />
      </div>

      {state.kind === "loading" ? (
        <p className="text-sm text-muted-foreground">Loading applications…</p>
      ) : state.kind === "error" ? (
        <StateMessage title={state.message} />
      ) : data && data.items.length === 0 ? (
        <StateMessage
          title={debounced || status !== ALL || stateCode ? "No applications match." : "No applications yet"}
        />
      ) : data ? (
        <>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Application</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Instrument</TableHead>
                <TableHead>Type</TableHead>
                <TableHead>Business</TableHead>
                <TableHead>State</TableHead>
                <TableHead>District</TableHead>
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
                  <TableCell>{a.organization_name}</TableCell>
                  <TableCell>{a.state_code}</TableCell>
                  <TableCell>{a.district_code}</TableCell>
                  <TableCell className="text-sm">
                    {a.submitted_at ? new Date(a.submitted_at).toLocaleDateString() : "—"}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>

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

export default function AdminApplicationsPage() {
  const { user } = useAuth();
  if (!user || user.role !== "SUPER_ADMIN") return <StateMessage title={NO_ACCESS} />;
  return (
    <Suspense>
      <AdminApplicationsList />
    </Suspense>
  );
}
