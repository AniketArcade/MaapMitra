"use client";

import { useEffect, useState } from "react";

import { ActiveBadge } from "@/components/admin/active-badge";
import { UserCreateForm } from "@/components/admin/user-create-form";
import { NO_ACCESS, StateMessage } from "@/components/instruments/state-message";
import { SelectField } from "@/components/select-field";
import { buttonVariants } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
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
const ALL = "__all__";
const ROLE_OPTIONS = [
  { value: ALL, label: "All roles" },
  { value: "SUPER_ADMIN", label: "Super Admin" },
  { value: "STATE_ADMIN", label: "State Admin" },
  { value: "DISTRICT_ADMIN", label: "District Admin" },
  { value: "LM_OFFICER", label: "LM Officer" },
];

type State =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "ready"; data: Page<AdminUser> };

// Spec 17 §6.6: official-account directory + Create + per-row Activate/Deactivate.
function UsersList() {
  const [instrumentMeta, setInstrumentMeta] = useState<InstrumentMeta | null>(null);
  const [query, setQuery] = useState("");
  const [debounced, setDebounced] = useState("");
  const [role, setRole] = useState(ALL);
  const [stateCode, setStateCode] = useState("");
  const [districtCode, setDistrictCode] = useState("");
  const [isActive, setIsActive] = useState<"" | "true" | "false">("");
  const [page, setPage] = useState(1);
  const [state, setState] = useState<State>({ kind: "loading" });
  const [refreshNonce, setRefreshNonce] = useState(0);
  const [createOpen, setCreateOpen] = useState(false);

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
    if (role !== ALL) params.set("role", role);
    if (stateCode) params.set("state_code", stateCode);
    if (districtCode) params.set("district_code", districtCode);
    if (isActive) params.set("is_active", isActive);
    getUsers(params).then(
      (data) => !cancelled && setState({ kind: "ready", data }),
      (err: unknown) => {
        if (cancelled) return;
        const message =
          err instanceof ApiError && err.status === 403
            ? "You don't have access to user management."
            : "Could not load users.";
        setState({ kind: "error", message });
      },
    );
    return () => {
      cancelled = true;
    };
  }, [debounced, role, stateCode, districtCode, isActive, page, refreshNonce]);

  async function toggle(userId: string, nextActive: boolean) {
    await patchUserActive(userId, nextActive);
    setRefreshNonce((n) => n + 1);
  }

  function onCreated() {
    setCreateOpen(false);
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
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">Users</h1>
          <p className="text-sm text-muted-foreground">Official accounts: admins and officers.</p>
        </div>
        <button type="button" className={buttonVariants()} onClick={() => setCreateOpen(true)}>
          Create official account
        </button>
      </div>

      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Create official account</DialogTitle>
          </DialogHeader>
          <UserCreateForm onCreated={onCreated} />
        </DialogContent>
      </Dialog>

      <div className="grid gap-3 sm:grid-cols-[1fr_10rem_10rem_10rem_8rem]">
        <Input
          type="search"
          placeholder="Search by name or email"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          maxLength={100}
          className="h-10"
          aria-label="Search users"
        />
        <SelectField
          name="role_filter"
          label="Role"
          value={role}
          options={ROLE_OPTIONS}
          onChange={(v) => {
            setRole(v || ALL);
            setPage(1);
          }}
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
        <p className="text-sm text-muted-foreground">Loading users…</p>
      ) : state.kind === "error" ? (
        <StateMessage title={state.message} />
      ) : data && data.items.length === 0 ? (
        <StateMessage title="No users match." />
      ) : data ? (
        <>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>Email</TableHead>
                <TableHead>Role</TableHead>
                <TableHead>State</TableHead>
                <TableHead>District</TableHead>
                <TableHead>Status</TableHead>
                <TableHead />
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.items.map((u) => (
                <TableRow key={u.id}>
                  <TableCell>{u.full_name}</TableCell>
                  <TableCell className="text-sm">{u.email}</TableCell>
                  <TableCell>{u.role}</TableCell>
                  <TableCell>{u.state_code ?? "—"}</TableCell>
                  <TableCell>{u.district_code ?? "—"}</TableCell>
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
              {data.total} user{data.total === 1 ? "" : "s"}
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

export default function UsersPage() {
  const { user } = useAuth();
  if (!user || user.role !== "SUPER_ADMIN") return <StateMessage title={NO_ACCESS} />;
  return <UsersList />;
}
