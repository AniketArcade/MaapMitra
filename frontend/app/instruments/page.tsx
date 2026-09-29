"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { StateMessage } from "@/components/instruments/state-message";
import { Badge } from "@/components/ui/badge";
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
import { getInstrumentMeta, regionLabel, typeLabel } from "@/lib/meta";
import type { Instrument, InstrumentMeta, Page } from "@/lib/types";

const PAGE_SIZE = 20;

type State =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "ready"; data: Page<Instrument> };

export default function InstrumentsPage() {
  const { user } = useAuth();
  const isBusiness = user?.role === "BUSINESS";
  const [meta, setMeta] = useState<InstrumentMeta | null>(null);
  const [query, setQuery] = useState("");
  const [debounced, setDebounced] = useState("");
  const [page, setPage] = useState(1);
  const [state, setState] = useState<State>({ kind: "loading" });

  useEffect(() => {
    getInstrumentMeta().then(setMeta, () => undefined); // labels only; codes are a fallback
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
    api<Page<Instrument>>(`/instruments?${params}`).then(
      (data) => !cancelled && setState({ kind: "ready", data }),
      (err: unknown) => {
        if (cancelled) return;
        const message =
          err instanceof ApiError && err.status === 403
            ? "You don't have access to instruments."
            : "Could not load instruments.";
        setState({ kind: "error", message });
      },
    );
    return () => {
      cancelled = true;
    };
  }, [debounced, page]);

  const data = state.kind === "ready" ? state.data : null;
  const lastPage = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1;

  return (
    <div className="grid gap-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">Instruments</h1>
          {!isBusiness ? (
            <p className="text-sm text-muted-foreground">Read-only view of your jurisdiction.</p>
          ) : null}
        </div>
        {isBusiness ? (
          <Link href="/instruments/new" className={buttonVariants()}>
            Register instrument
          </Link>
        ) : null}
      </div>

      <Input
        type="search"
        placeholder="Search by serial, UID, manufacturer or model"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        maxLength={100}
        className="h-10 max-w-md"
        aria-label="Search instruments"
      />

      {state.kind === "loading" ? (
        <p className="text-sm text-muted-foreground">Loading instruments…</p>
      ) : state.kind === "error" ? (
        <StateMessage title={state.message} />
      ) : data && data.items.length === 0 ? (
        debounced ? (
          <StateMessage title="No instruments match your search." />
        ) : (
          <StateMessage title="No instruments yet">
            {isBusiness ? (
              <Link href="/instruments/new" className="underline">
                Register one
              </Link>
            ) : (
              "No instruments are registered in your jurisdiction."
            )}
          </StateMessage>
        )
      ) : data ? (
        <>
          {/* Cards on mobile */}
          <ul className="grid gap-3 md:hidden">
            {data.items.map((i) => (
              <li key={i.id}>
                <Link href={`/instruments/${i.id}`} className="grid gap-1 rounded-lg border p-4">
                  <span className="font-mono text-xs text-muted-foreground">{i.instrument_uid}</span>
                  <span className="font-medium">
                    {typeLabel(meta, i.instrument_type)} · {i.capacity} {i.capacity_unit}
                  </span>
                  <span className="text-sm text-muted-foreground">
                    {i.manufacturer} {i.model} · S/N {i.serial_number}
                  </span>
                  {!isBusiness ? <span className="text-sm">{i.organization_name}</span> : null}
                </Link>
              </li>
            ))}
          </ul>

          {/* Table on desktop */}
          <div className="hidden md:block">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>UID</TableHead>
                  <TableHead>Type</TableHead>
                  <TableHead>Serial</TableHead>
                  <TableHead>Manufacturer / model</TableHead>
                  <TableHead>Capacity</TableHead>
                  <TableHead>Location</TableHead>
                  {!isBusiness ? <TableHead>Owner</TableHead> : null}
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.items.map((i) => (
                  <TableRow key={i.id}>
                    <TableCell>
                      <Link href={`/instruments/${i.id}`} className="font-mono text-xs underline">
                        {i.instrument_uid}
                      </Link>
                    </TableCell>
                    <TableCell>
                      <Badge variant="secondary">{typeLabel(meta, i.instrument_type)}</Badge>
                    </TableCell>
                    <TableCell className="font-mono text-xs">{i.serial_number}</TableCell>
                    <TableCell>
                      {i.manufacturer} {i.model}
                    </TableCell>
                    <TableCell>
                      {i.capacity} {i.capacity_unit}
                    </TableCell>
                    <TableCell>{regionLabel(meta, i.state_code, i.district_code)}</TableCell>
                    {!isBusiness ? <TableCell>{i.organization_name}</TableCell> : null}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>

          <div className="flex items-center justify-between text-sm text-muted-foreground">
            <span>
              {data.total} instrument{data.total === 1 ? "" : "s"}
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
