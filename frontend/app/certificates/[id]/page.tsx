"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import { StateMessage } from "@/components/instruments/state-message";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { ApiError, api, getCertificate } from "@/lib/api";
import type { Certificate } from "@/lib/types";

type State =
  | { kind: "loading" }
  | { kind: "not-found" }
  | { kind: "error" }
  | { kind: "ready"; certificate: Certificate };

function errorMessage(err: unknown): string {
  if (!(err instanceof ApiError)) return "Could not reach the server.";
  return err.message;
}

export default function CertificateDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [state, setState] = useState<State>({ kind: "loading" });
  const [actionError, setActionError] = useState<string | null>(null);

  useEffect(() => {
    getCertificate(id).then(
      (certificate) => setState({ kind: "ready", certificate }),
      (err: unknown) => {
        setState(err instanceof ApiError && err.status === 404 ? { kind: "not-found" } : { kind: "error" });
      },
    );
  }, [id]);

  if (state.kind === "loading") return <p className="text-sm text-muted-foreground">Loading…</p>;
  if (state.kind === "not-found") return <StateMessage title="Certificate not found" />;
  if (state.kind === "error") return <StateMessage title="Could not load this certificate." />;

  const certificate = state.certificate;

  async function onView() {
    setActionError(null);
    const tab = window.open("", "_blank");
    try {
      const { url } = await api<{ url: string; expires_in: number }>(
        `/certificates/${certificate.id}/pdf?disposition=inline`,
      );
      if (tab) {
        tab.opener = null;
        tab.location.href = url;
      } else {
        window.location.href = url;
      }
    } catch (err) {
      tab?.close();
      setActionError(errorMessage(err));
    }
  }

  async function onDownload() {
    setActionError(null);
    try {
      const { url } = await api<{ url: string; expires_in: number }>(
        `/certificates/${certificate.id}/pdf?disposition=attachment`,
      );
      window.location.assign(url);
    } catch (err) {
      setActionError(errorMessage(err));
    }
  }

  return (
    <div className="grid gap-6">
      <div className="grid gap-1">
        <span className="font-mono text-sm text-muted-foreground">
          {certificate.certificate_number}
        </span>
        <h1 className="text-2xl font-semibold">Certificate of Verification</h1>
        <p className="text-sm text-muted-foreground">
          {certificate.manufacturer} {certificate.model} · S/N {certificate.serial_number} ·{" "}
          {certificate.organization_name}
        </p>
      </div>

      {actionError ? (
        <Alert variant="destructive">
          <AlertDescription>{actionError}</AlertDescription>
        </Alert>
      ) : null}

      {certificate.is_expiring_soon ? (
        <p className="text-sm font-medium text-amber-600 dark:text-amber-500">
          Expiring soon — a re-verification may be needed shortly.
        </p>
      ) : null}
      {certificate.superseded_by_certificate_id ? (
        <p className="text-sm text-muted-foreground">
          This certificate has been superseded.{" "}
          <Link
            href={`/certificates/${certificate.superseded_by_certificate_id}`}
            className="underline"
          >
            View the current certificate
          </Link>
        </p>
      ) : null}
      {certificate.supersedes_certificate_id ? (
        <p className="text-xs text-muted-foreground">
          Supersedes an earlier certificate.{" "}
          <Link
            href={`/certificates/${certificate.supersedes_certificate_id}`}
            className="underline"
          >
            View it
          </Link>
        </p>
      ) : null}

      <div className="grid gap-4 rounded-lg border p-4 sm:grid-cols-[auto_1fr] sm:items-start">
        {/* eslint-disable-next-line @next/next/no-img-element -- a short-lived base64 data URI, not a served asset */}
        <img
          src={certificate.qr_code_data_uri}
          alt="QR code linking to the public verification page"
          className="h-32 w-32"
        />
        <dl className="grid gap-1 text-sm">
          <div className="flex justify-between gap-2">
            <dt className="text-muted-foreground">Instrument</dt>
            <dd>{certificate.instrument_uid}</dd>
          </div>
          <div className="flex justify-between gap-2">
            <dt className="text-muted-foreground">Capacity</dt>
            <dd>
              {certificate.capacity} {certificate.capacity_unit}
            </dd>
          </div>
          <div className="flex justify-between gap-2">
            <dt className="text-muted-foreground">Status</dt>
            <dd>{certificate.status}</dd>
          </div>
          <div className="flex justify-between gap-2">
            <dt className="text-muted-foreground">Valid from</dt>
            <dd>{new Date(certificate.valid_from).toLocaleDateString()}</dd>
          </div>
          <div className="flex justify-between gap-2">
            <dt className="text-muted-foreground">Valid until</dt>
            <dd>{new Date(certificate.valid_until).toLocaleDateString()}</dd>
          </div>
        </dl>
      </div>

      <div className="flex gap-2">
        <Button variant="outline" onClick={() => void onView()}>
          View PDF
        </Button>
        <Button variant="ghost" onClick={() => void onDownload()}>
          Download
        </Button>
      </div>
    </div>
  );
}
