"use client";

import { useEffect, useState } from "react";

import { ActiveBadge } from "@/components/admin/active-badge";
import { NO_ACCESS, StateMessage } from "@/components/instruments/state-message";
import { Badge } from "@/components/ui/badge";
import { buttonVariants } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { SelectField } from "@/components/select-field";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { ApiError, getGatcDirectory, patchUserActive } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { getInstrumentMeta } from "@/lib/meta";
import type { GatcDirectoryEntry, InstrumentMeta, Page } from "@/lib/types";

const PAGE_SIZE = 20;

type State =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "ready"; data: Page<GatcDirectoryEntry> };

// Spec 17 §6.5: a read-only directory of GATC organizations, plus per-person Activate/Deactivate
// (PATCH /api/users/{id} — the same action the Users/LMO pages use; there is no org-level
// is_active column, see GatcDirectoryEntry.active's roll-up definition in lib/types.ts).
function GatcDirectoryList() {
  const [instrumentMeta, setInstrumentMeta] = useState<InstrumentMeta | null>(null);
  const [query, setQuery] = useState("");
  const [debounced, setDebounced] = useState("");
  const [stateCode, setStateCode] = useState("");
  const [districtCode, setDistrictCode] = useState("");
  const [isActive, setIsActive] = useState<"" | "true" | "false">("");
  const [page, setPage] = useState(1);
  const [state, setState] = useState<State>({ kind: "loading" });
  const [refreshNonce, setRefreshNonce] = useState(0);

  useEffect(() => {
    getInstrumentMeta().then(setInstrumentMeta, () => undefined);
  }, []);

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
    if (stateCode) params.set("state_code", stateCode);
    if (districtCode) params.set("district_code", districtCode);
    if (isActive) params.set("is_active", isActive);
    getGatcDirectory(params).then(
      (data) => !cancelled && setState({ kind: "ready", data }),
      (err: unknown) => {
        if (cancelled) return;
        const message =
          err instanceof ApiError && err.status === 403
            ? "You don't have access to the GATC directory."
            : "Could not load GATC organizations.";
        setState({ kind: "error", message });
      },
    );
    return () => {
      cancelled = true;
    };
  }, [debounced, stateCode, districtCode, isActive, page, refreshNonce]);

  async function toggle(userId: string, nextActive: boolean) {
    await patchUserActive(userId, nextActive);
    setRefreshNonce((n) => n + 1);
  }

  const data = state.kind === "ready" ? state.data : null;
  const lastPage = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1;
  const districtsForState =
    instrumentMeta?.regions.find((r) => r.state_code === stateCode)?.districts ?? [];
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
        <h1 className="text-2xl font-semibold">GATC directory</h1>
        <p className="text-sm text-muted-foreground">
          Government Approved Test Centres, nationwide.
        </p>
      </div>

      <div className="grid gap-3 sm:grid-cols-[1fr_10rem_10rem_8rem]">
        <Input
          type="search"
          placeholder="Search by organization name"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          maxLength={100}
          className="h-10"
          aria-label="Search GATC organizations"
        />
        <SelectField
          name="state_filter"
          label="State"
          value={stateCode}
          options={stateOptions}
          onChange={(v) => {
            setStateCode(v);
            setDistrictCode("");
            setPage(1);
          }}
        />
        <SelectField
          name="district_filter"
          label="District"
          value={districtCode}
          options={districtOptions}
          onChange={(v) => {
            setDistrictCode(v);
            setPage(1);
          }}
          disabled={!stateCode}
        />
        <SelectField
          name="active_filter"
          label="Status"
          value={isActive}
          options={[
            { value: "", label: "All" },
            { value: "true", label: "Active" },
            { value: "false", label: "Inactive" },
          ]}
          onChange={(v) => {
            setIsActive(v as "" | "true" | "false");
            setPage(1);
          }}
        />
      </div>

      {state.kind === "loading" ? (
        <p className="text-sm text-muted-foreground">Loading…</p>
      ) : state.kind === "error" ? (
        <StateMessage title={state.message} />
      ) : data && data.items.length === 0 ? (
        <StateMessage title="No GATC organizations match." />
      ) : data ? (
        <>
          <div className="grid gap-4">
            {data.items.map((org) => (
              <div key={org.id} className="rounded-lg border p-4">
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div>
                    <h2 className="font-medium">{org.name}</h2>
                    <p className="text-sm text-muted-foreground">
                      {org.district_code}, {org.state_code}
                    </p>
                  </div>
                  <ActiveBadge active={org.active} />
                </div>
                <div className="mt-2 flex flex-wrap gap-1">
                  {org.eligible_categories.length === 0 ? (
                    <span className="text-sm text-muted-foreground">No categories configured</span>
                  ) : (
                    org.eligible_categories.map((c) => (
                      <Badge key={c} variant="secondary">
                        {c}
                      </Badge>
                    ))
                  )}
                </div>
                <div className="mt-2 text-sm text-muted-foreground">
                  {org.pending_cases} pending · {org.completed_cases} completed
                </div>
                <Table className="mt-3">
                  <TableHeader>
                    <TableRow>
                      <TableHead>Name</TableHead>
                      <TableHead>Email</TableHead>
                      <TableHead>Status</TableHead>
                      <TableHead />
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {org.users.map((u) => (
                      <TableRow key={u.id}>
                        <TableCell>{u.full_name}</TableCell>
                        <TableCell className="text-sm">{u.email}</TableCell>
                        <TableCell>
                          <ActiveBadge active={u.is_active} />
                        </TableCell>
                        <TableCell className="text-right">
                          <button
                            type="button"
                            className={buttonVariants({ variant: "outline", size: "sm" })}
                            onClick={() => void toggle(u.id, !u.is_active)}
                          >
                            {u.is_active ? "Deactivate" : "Activate"}
                          </button>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            ))}
          </div>

          <div className="flex items-center justify-between text-sm text-muted-foreground">
            <span>
              {data.total} organization{data.total === 1 ? "" : "s"}
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

export default function GatcDirectoryPage() {
  const { user } = useAuth();
  if (!user || user.role !== "SUPER_ADMIN") return <StateMessage title={NO_ACCESS} />;
  return <GatcDirectoryList />;
}
