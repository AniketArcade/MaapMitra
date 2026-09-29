"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState, type ChangeEvent } from "react";

import { StatusBadge } from "@/components/applications/status-badge";
import { NO_ACCESS, StateMessage } from "@/components/instruments/state-message";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { ApiError, api, uploadDocument } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { getApplicationMeta, labelFor } from "@/lib/meta";
import type { ApplicationDetail, ApplicationMeta, DocumentOut } from "@/lib/types";

type State =
  | { kind: "loading" }
  | { kind: "not-found" }
  | { kind: "forbidden" }
  | { kind: "error" }
  | { kind: "ready"; app: ApplicationDetail };

const REJECT_MIN = 10;

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(0)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}

function errorMessage(err: unknown): string {
  if (!(err instanceof ApiError)) return "Could not reach the server.";
  const fieldMessage = Object.values(err.fieldErrors)[0];
  return fieldMessage ?? err.message;
}

export default function ApplicationDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { user } = useAuth();
  const [meta, setMeta] = useState<ApplicationMeta | null>(null);
  const [state, setState] = useState<State>({ kind: "loading" });
  const [uploading, setUploading] = useState<string | null>(null);
  const [uploadErrors, setUploadErrors] = useState<Record<string, string>>({});
  const [actionError, setActionError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [confirmSubmit, setConfirmSubmit] = useState(false);
  const [rejectOpen, setRejectOpen] = useState(false);
  const [rejectNote, setRejectNote] = useState("");

  const load = useCallback(async () => {
    try {
      const app = await api<ApplicationDetail>(`/applications/${id}`);
      setState({ kind: "ready", app });
    } catch (err) {
      if (err instanceof ApiError && (err.status === 404 || err.status === 422)) {
        setState({ kind: "not-found" });
      } else if (err instanceof ApiError && err.status === 403) {
        setState({ kind: "forbidden" });
      } else {
        setState({ kind: "error" });
      }
    }
  }, [id]);

  useEffect(() => {
    getApplicationMeta().then(setMeta, () => undefined);
    void load();
  }, [load]);

  if (state.kind === "loading") return <p className="text-sm text-muted-foreground">Loading…</p>;
  if (state.kind === "not-found") return <StateMessage title="Application not found" />;
  if (state.kind === "forbidden") return <StateMessage title={NO_ACCESS} />;
  if (state.kind === "error") return <StateMessage title="Could not load this application." />;

  const app = state.app;
  const isOwner = user?.role === "BUSINESS";
  const editable = isOwner && app.status === "DRAFT";
  const canSubmit = app.allowed_actions.includes("SUBMITTED");
  const requirementsMet = app.requirements.every((r) => !r.required || r.satisfied);
  const limits = meta?.limits;
  const atLimit = limits ? app.documents.length >= limits.max_documents : false;

  async function onFile(documentType: string, event: ChangeEvent<HTMLInputElement>) {
    const input = event.currentTarget;
    const file = input.files?.[0];
    input.value = ""; // allow re-selecting the same file after an error
    if (!file) return;
    setUploadErrors((prev) => ({ ...prev, [documentType]: "" }));
    // Convenience pre-checks only: the server sniffs the real type and enforces the size.
    if (limits && file.size > limits.max_file_bytes) {
      setUploadErrors((prev) => ({ ...prev, [documentType]: "File is too large (maximum 10 MB)" }));
      return;
    }
    if (limits && file.type && !limits.allowed_content_types.includes(file.type)) {
      setUploadErrors((prev) => ({ ...prev, [documentType]: "Only PDF, JPG and PNG files are allowed" }));
      return;
    }
    const form = new FormData();
    form.append("application_id", app.id);
    form.append("document_type", documentType);
    form.append("file", file);
    setUploading(documentType);
    try {
      await uploadDocument<DocumentOut>(form);
      await load();
    } catch (err) {
      setUploadErrors((prev) => ({ ...prev, [documentType]: errorMessage(err) }));
    } finally {
      setUploading(null);
    }
  }

  async function onView(documentId: string) {
    // Open the tab synchronously (inside the click) so popup blockers allow it,
    // then point it at the short-lived signed URL.
    const tab = window.open("", "_blank");
    try {
      const { url } = await api<{ url: string; expires_in: number }>(`/documents/${documentId}/url`);
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

  async function onDeleteDocument(documentId: string) {
    setActionError(null);
    try {
      await api<void>(`/documents/${documentId}`, { method: "DELETE" });
      await load();
    } catch (err) {
      setActionError(errorMessage(err));
    }
  }

  async function changeStatus(status: string, note?: string) {
    setBusy(true);
    setActionError(null);
    try {
      const updated = await api<ApplicationDetail>(`/applications/${app.id}/status`, {
        method: "PATCH",
        body: JSON.stringify(note ? { status, note } : { status }),
      });
      setState({ kind: "ready", app: updated });
      setConfirmSubmit(false);
      setRejectOpen(false);
      setRejectNote("");
    } catch (err) {
      setActionError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  const documentsByType = (type: string) => app.documents.filter((d) => d.document_type === type);
  const shownTypes = editable
    ? app.requirements
    : app.requirements.filter((r) => r.required || documentsByType(r.document_type).length > 0);

  return (
    <div className="grid gap-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="grid gap-1">
          <span className="font-mono text-sm text-muted-foreground">{app.application_number}</span>
          <h1 className="text-2xl font-semibold">
            {labelFor(meta?.application_types, app.application_type)}
          </h1>
          <p className="text-sm text-muted-foreground">
            <Link href={`/instruments/${app.instrument.id}`} className="underline">
              {app.instrument.instrument_uid}
            </Link>{" "}
            · {app.instrument.manufacturer} {app.instrument.model} · S/N {app.instrument.serial_number} ·{" "}
            {app.instrument.capacity} {app.instrument.capacity_unit}
            {!isOwner ? ` · ${app.organization_name}` : ""}
          </p>
        </div>
        <StatusBadge status={app.status} label={labelFor(meta?.statuses, app.status)} />
      </div>

      {actionError ? (
        <Alert variant="destructive">
          <AlertDescription>{actionError}</AlertDescription>
        </Alert>
      ) : null}

      {/* Actions come from allowed_actions: the UI never guesses permissions. */}
      {app.allowed_actions.length > 0 ? (
        <div className="flex flex-wrap gap-2">
          {canSubmit ? (
            <Button onClick={() => setConfirmSubmit(true)} disabled={!requirementsMet || busy}>
              Submit application
            </Button>
          ) : null}
          {app.allowed_actions.includes("DOCUMENT_REVIEW") ? (
            <Button onClick={() => void changeStatus("DOCUMENT_REVIEW")} disabled={busy}>
              {busy ? "Starting…" : "Start review"}
            </Button>
          ) : null}
          {app.allowed_actions.includes("REJECTED") ? (
            <Button variant="destructive" onClick={() => setRejectOpen(true)} disabled={busy}>
              Reject
            </Button>
          ) : null}
        </div>
      ) : null}
      {canSubmit && !requirementsMet ? (
        <p className="-mt-3 text-sm text-muted-foreground">Upload every required document to submit.</p>
      ) : null}

      <section className="grid gap-3">
        <h2 className="text-lg font-medium">Documents</h2>
        {editable && limits ? (
          <p className="text-sm text-muted-foreground">
            PDF, JPG or PNG, up to {formatBytes(limits.max_file_bytes)} each, {limits.max_documents} files
            in total.
          </p>
        ) : null}
        <ul className="grid gap-3">
          {shownTypes.map((r) => {
            const docs = documentsByType(r.document_type);
            return (
              <li key={r.document_type} className="grid gap-2 rounded-lg border p-4">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="font-medium">
                    {r.satisfied ? "✓" : r.required ? "✗" : "•"} {r.label}
                    <span className="ml-2 text-xs font-normal text-muted-foreground">
                      {r.required ? "Required" : "Optional"}
                    </span>
                  </span>
                  {editable ? (
                    <Label
                      className={
                        atLimit || uploading
                          ? "pointer-events-none opacity-50"
                          : "cursor-pointer rounded-md border px-3 py-1.5 text-sm hover:bg-muted"
                      }
                    >
                      {uploading === r.document_type ? "Uploading…" : "Upload file"}
                      <input
                        type="file"
                        accept="application/pdf,image/jpeg,image/png"
                        className="sr-only"
                        disabled={atLimit || uploading !== null}
                        onChange={(e) => void onFile(r.document_type, e)}
                      />
                    </Label>
                  ) : null}
                </div>
                {uploadErrors[r.document_type] ? (
                  <p className="text-sm text-destructive">{uploadErrors[r.document_type]}</p>
                ) : null}
                {docs.length > 0 ? (
                  <ul className="grid gap-1 text-sm">
                    {docs.map((d) => (
                      <li key={d.id} className="flex flex-wrap items-center justify-between gap-2">
                        <span className="break-all">
                          {d.original_filename}{" "}
                          <span className="text-muted-foreground">({formatBytes(d.size_bytes)})</span>
                        </span>
                        <span className="flex gap-2">
                          <Button variant="outline" size="sm" onClick={() => void onView(d.id)}>
                            View
                          </Button>
                          {editable ? (
                            <Button variant="ghost" size="sm" onClick={() => void onDeleteDocument(d.id)}>
                              Remove
                            </Button>
                          ) : null}
                        </span>
                      </li>
                    ))}
                  </ul>
                ) : null}
              </li>
            );
          })}
        </ul>
      </section>

      {app.business_notes ? (
        <section className="grid gap-1">
          <h2 className="text-lg font-medium">Notes from the business</h2>
          <p className="whitespace-pre-wrap text-sm">{app.business_notes}</p>
        </section>
      ) : null}

      <section className="grid gap-3">
        <h2 className="text-lg font-medium">Timeline</h2>
        <ol className="grid gap-3 border-l pl-4">
          {app.history.map((h, index) => (
            <li key={index} className="grid gap-0.5">
              <span className="text-sm font-medium">{labelFor(meta?.statuses, h.to_status)}</span>
              <span className="text-xs text-muted-foreground">
                {new Date(h.created_at).toLocaleString()} · {h.actor_name}
              </span>
              {h.note ? <span className="whitespace-pre-wrap text-sm">{h.note}</span> : null}
            </li>
          ))}
        </ol>
      </section>

      <Dialog open={confirmSubmit} onOpenChange={setConfirmSubmit}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Submit this application?</DialogTitle>
            <DialogDescription>
              After submitting you can&apos;t add or remove documents, and the instrument&apos;s details stay
              locked until the application is decided.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirmSubmit(false)} disabled={busy}>
              Cancel
            </Button>
            <Button onClick={() => void changeStatus("SUBMITTED")} disabled={busy}>
              {busy ? "Submitting…" : "Submit"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={rejectOpen} onOpenChange={setRejectOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Reject this application?</DialogTitle>
            <DialogDescription>
              This can&apos;t be undone. The business will see your reason and must re-apply.
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-1.5">
            <Label htmlFor="reject_note">Reason</Label>
            <Textarea
              id="reject_note"
              value={rejectNote}
              maxLength={1000}
              onChange={(e) => setRejectNote(e.target.value)}
            />
            <p className="text-xs text-muted-foreground">At least {REJECT_MIN} characters.</p>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setRejectOpen(false)} disabled={busy}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={() => void changeStatus("REJECTED", rejectNote.trim())}
              disabled={busy || rejectNote.trim().length < REJECT_MIN}
            >
              {busy ? "Rejecting…" : "Reject"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
