"use client";

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import { StateMessage } from "@/components/instruments/state-message";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { ApiError, getPublicVerify } from "@/lib/api";
import type { VerifyResult } from "@/lib/types";

type State =
  | { kind: "loading" }
  | { kind: "not-found" }
  | { kind: "error" }
  | { kind: "ready"; result: VerifyResult };

const BADGE: Record<string, { label: string; className: string }> = {
  VALID: { label: "✓ VALID", className: "bg-green-100 text-green-800" },
  EXPIRED: { label: "⚠ EXPIRED", className: "bg-amber-100 text-amber-800" },
  REVOKED: { label: "✕ REVOKED", className: "bg-red-100 text-red-800" },
  SUPERSEDED: { label: "⚠ SUPERSEDED", className: "bg-amber-100 text-amber-800" },
};

export default function VerifyPage() {
  const { certificateNumber } = useParams<{ certificateNumber: string }>();
  const [state, setState] = useState<State>({ kind: "loading" });

  useEffect(() => {
    getPublicVerify(certificateNumber).then(
      (result) => setState({ kind: "ready", result }),
      (err: unknown) => {
        setState(err instanceof ApiError && err.status === 404 ? { kind: "not-found" } : { kind: "error" });
      },
    );
  }, [certificateNumber]);

  if (state.kind === "loading") return <p className="text-sm text-muted-foreground">Checking…</p>;
  if (state.kind === "not-found") return <StateMessage title="Certificate not found" />;
  if (state.kind === "error") {
    return <StateMessage title="Couldn't check this certificate. Try again." />;
  }

  const { result } = state;
  const badge = BADGE[result.status] ?? { label: result.status, className: "bg-muted" };

  return (
    <Card className="w-full max-w-sm">
      <CardHeader>
        <span className="font-mono text-xs text-muted-foreground">{result.certificate_number}</span>
      </CardHeader>
      <CardContent className="grid gap-4">
        <div
          className={`rounded-lg px-4 py-3 text-center text-lg font-semibold ${badge.className}`}
        >
          {badge.label}
        </div>
        <dl className="grid gap-1 text-sm">
          <div className="flex justify-between gap-2">
            <dt className="text-muted-foreground">Instrument</dt>
            <dd>{result.instrument_type_label}</dd>
          </div>
          <div className="flex justify-between gap-2">
            <dt className="text-muted-foreground">Instrument ID</dt>
            <dd>{result.instrument_uid}</dd>
          </div>
          <div className="flex justify-between gap-2">
            <dt className="text-muted-foreground">Manufacturer</dt>
            <dd>{result.manufacturer}</dd>
          </div>
          <div className="flex justify-between gap-2">
            <dt className="text-muted-foreground">Model</dt>
            <dd>{result.model}</dd>
          </div>
          <div className="flex justify-between gap-2">
            <dt className="text-muted-foreground">Serial number</dt>
            <dd>{result.serial_number}</dd>
          </div>
          <div className="flex justify-between gap-2">
            <dt className="text-muted-foreground">Valid</dt>
            <dd>
              {new Date(result.valid_from).toLocaleDateString()} –{" "}
              {new Date(result.valid_until).toLocaleDateString()}
            </dd>
          </div>
          <div className="flex justify-between gap-2">
            <dt className="text-muted-foreground">Issued by</dt>
            <dd>{result.issued_by}</dd>
          </div>
        </dl>
      </CardContent>
    </Card>
  );
}
