"use client";

import { useEffect, useState } from "react";

import { ActiveBadge } from "@/components/admin/active-badge";
import { NO_ACCESS, StateMessage } from "@/components/instruments/state-message";
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
import { ApiError, getUsers, patchUserActive } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { getInstrumentMeta } from "@/lib/meta";
import type { AdminUser, InstrumentMeta, Page } from "@/lib/types";

const PAGE_SIZE = 20;

type State =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "ready"; data: Page<AdminUser> };

// Spec 17 §6.5: one row per LM Officer, reusing GET /api/users?role=LM_OFFICER (which is how
// pending_cases/completed_cases get populated — see lib/types.ts's AdminUser comment). Spec 18:
// for a STATE_ADMIN viewer, GET /api/users rejects (422) a state_code that mismatches their own —
// unlike organizations/applications, which just AND to an empty page — so the State filter is
// hidden entirely here rather than left to fail. The backend already forces state_code to the
// caller's own state when the param is omitted, so simply never sending it is correct.
function LmoDirectoryList() {
  const { user } = useAuth();
  const isStateAdmin = user?.role === "STATE_ADMIN";
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
    const params = new URLSearchParams({
      role: "LM_OFFICER",
      page: String(page),
      page_size: String(PAGE_SIZE),
    });
    if (debounced) params.set("q", debounced);
    if (stateCode && !isStateAdmin) params.set("state_code", stateCode);
    if (districtCode) params.set("district_code", districtCode);
    if (isActive) params.set("is_active", isActive);
    getUsers(params).then(
      (data) => !cancelled && setState({ kind: "ready", data }),
      (err: unknown) => {
        if (cancelled) return;
        const message =
          err instanceof ApiError && err.status === 403
            ? "You don't have access to the LMO directory."
            : "Could not load LM Officers.";
        setState({ kind: "error", message });
      },
    );
    return () => {
      cancelled = true;
    };
  }, [debounced, stateCode, districtCode, isActive, page, refreshNonce, isStateAdmin]);

  async function toggle(userId: string, nextActive: boolean) {
    await patchUserActive(userId, nextActive);
    setRefreshNonce((n) => n + 1);
  }

  const data = state.kind === "ready" ? state.data : null;
  const lastPage = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1;
  const effectiveStateCode = isStateAdmin ? (user?.state_code ?? "") : stateCode;
  const districtsForState =
    instrumentMeta?.regions.find((r) => r.state_code === effectiveStateCode)?.districts ?? [];
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
        <h1 className="text-2xl font-semibold">LMO directory</h1>
        <p className="text-sm text-muted-foreground">Legal Metrology Officers, nationwide.</p>
      </div>

      <div
        className={`grid gap-3 ${isStateAdmin ? "sm:grid-cols-[1fr_10rem_8rem]" : "sm:grid-cols-[1fr_10rem_10rem_8rem]"}`}
      >
        <Input
          type="search"
          placeholder="Search by name or email"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          maxLength={100}
          className="h-10"
          aria-label="Search LM Officers"
        />
        {isStateAdmin ? null : (
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
        )}
        <SelectField
          name="district_filter"
          label="District"
          value={districtCode}
          options={districtOptions}
          onChange={(v) => {
            setDistrictCode(v);
            setPage(1);
          }}
          disabled={!effectiveStateCode}
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
        <StateMessage title="No LM Officers match." />
      ) : data ? (
        <>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>Email</TableHead>
                {isStateAdmin ? null : <TableHead>State</TableHead>}
                <TableHead>District</TableHead>
                <TableHead>Pending</TableHead>
                <TableHead>Completed</TableHead>
                <TableHead>Status</TableHead>
                <TableHead />
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.items.map((u) => (
                <TableRow key={u.id}>
                  <TableCell>{u.full_name}</TableCell>
                  <TableCell className="text-sm">{u.email}</TableCell>
                  {isStateAdmin ? null : <TableCell>{u.state_code}</TableCell>}
                  <TableCell>{u.district_code}</TableCell>
                  <TableCell>{u.pending_cases ?? 0}</TableCell>
                  <TableCell>{u.completed_cases ?? 0}</TableCell>
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

          <div className="flex items-center justify-between text-sm text-muted-foreground">
            <span>
              {data.total} officer{data.total === 1 ? "" : "s"}
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

export default function LmoDirectoryPage() {
  const { user } = useAuth();
  if (!user || !["SUPER_ADMIN", "STATE_ADMIN"].includes(user.role)) {
    return <StateMessage title={NO_ACCESS} />;
  }
  return <LmoDirectoryList />;
}
