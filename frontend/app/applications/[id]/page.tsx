"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState, type ChangeEvent } from "react";

import { StatusBadge } from "@/components/applications/status-badge";
import { NO_ACCESS, StateMessage } from "@/components/instruments/state-message";
import { SelectField } from "@/components/select-field";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { ApiError, api, getGatcEligible, getGatcOrgUsers, uploadDocument } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { getApplicationMeta, labelFor } from "@/lib/meta";
import { addDaysToIsoDate, todayInTimezone } from "@/lib/scheduling";
import type {
  ApplicationDetail,
  ApplicationMeta,
  DocumentOut,
  GatcEligibleOrg,
  GatcOrgUser,
  Instrument,
} from "@/lib/types";

type State =
  | { kind: "loading" }
  | { kind: "not-found" }
  | { kind: "forbidden" }
  | { kind: "error" }
  | { kind: "ready"; app: ApplicationDetail };

const REJECT_MIN = 10;
// Step 11: mirrors the backend's DEFICIENCY_NOTE_MIN — a sibling constant, kept separate from
// REJECT_MIN so the two can diverge later without an unrelated rename (same reasoning the
// backend's own services/applications.py documents for itself).
const DEFICIENCY_MIN = 10;

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

// Spec 15: InspectionAssigneeRole is a small, self-evident, model-owned enum with no meta-exposed
// label dict (same precedent ChecklistResult already sets) — display labels are fine to compute
// inline here, unlike status/application_type/document_type, which always go through meta.
function assigneeRoleLabel(role: string): string {
  return role === "GATC" ? "GATC (test centre)" : "LM Officer";
}

export default function ApplicationDetailPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
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
  const [approveOpen, setApproveOpen] = useState(false);
  const [approveNote, setApproveNote] = useState("");
  const [deficientOpen, setDeficientOpen] = useState(false);
  const [deficientNote, setDeficientNote] = useState("");
  const [scheduleOpen, setScheduleOpen] = useState(false);
  const [scheduleDate, setScheduleDate] = useState("");
  const [rescheduleDate, setRescheduleDate] = useState("");
  const [reviewBusy, setReviewBusy] = useState<string | null>(null);
  const [payBusy, setPayBusy] = useState(false);

  // Spec 15: GATC routing choice, populated only while scheduling an OFFICE_TEST_CENTRE,
  // category-tagged application. `gatcEligible === null` means "not checked yet, or not
  // applicable" — an ON_SITE application (or one whose instrument has no category_id) never
  // triggers the extra fetches below, so its self-assign-only flow stays completely unchanged.
  const [gatcEligible, setGatcEligible] = useState<GatcEligibleOrg[] | null>(null);
  const [gatcLoading, setGatcLoading] = useState(false);
  const [gatcMode, setGatcMode] = useState<"self" | "gatc">("self");
  const [gatcOrgId, setGatcOrgId] = useState("");
  const [gatcUsers, setGatcUsers] = useState<GatcOrgUser[] | null>(null);
  const [gatcUserId, setGatcUserId] = useState("");

  useEffect(() => {
    if (meta && !scheduleDate) setScheduleDate(todayInTimezone(meta.scheduling.timezone));
  }, [meta, scheduleDate]);

  useEffect(() => {
    if (state.kind === "ready" && state.app.inspection && !rescheduleDate) {
      setRescheduleDate(state.app.inspection.scheduled_date);
    }
  }, [state, rescheduleDate]);

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
  const isOfficer = user?.role === "LM_OFFICER";
  const editable = isOwner && app.status === "DRAFT";
  const canSubmit = app.allowed_actions.includes("SUBMITTED");
  const canSchedule = app.allowed_actions.includes("SCHEDULED");
  const canStartInspection = app.allowed_actions.includes("INSPECTION");
  // Not allowed_actions-driven: (APPROVED, CERTIFICATE_ISSUED) is Edge(frozenset(), enabled=False)
  // in ALLOWED_TRANSITIONS — deliberately system-only, never a generic edge. This is the one
  // documented exception to "buttons come only from allowed_actions" (frontend/CLAUDE.md).
  const canIssueCertificate = app.status === "APPROVED" && isOfficer;
  const requirementsMet = app.requirements.every((r) => !r.required || r.satisfied);
  // Step 11: the backend is the source of truth (DOCUMENT_REVIEW -> SCHEDULED 409s with the
  // unchecked items' labels if this isn't true) — this only disables the button with a helpful
  // hint once the gate is already known, exactly like requirementsMet does for Submit above.
  const reviewChecklistComplete = app.review_checklist.every((i) => i.checked);
  const deficiencyNote =
    app.status === "DOCUMENTS_DEFICIENT"
      ? ([...app.history].reverse().find((h) => h.to_status === "DOCUMENTS_DEFICIENT")?.note ?? null)
      : null;
  const limits = meta?.limits;
  const atLimit = limits ? app.documents.length >= limits.max_documents : false;
  // Always computed in the backend's scheduling timezone, never the browser's local date;
  // the server validates independently regardless.
  const minScheduleDate = meta ? todayInTimezone(meta.scheduling.timezone) : undefined;
  const maxScheduleDate =
    meta && minScheduleDate
      ? addDaysToIsoDate(minScheduleDate, meta.scheduling.max_days_ahead)
      : undefined;

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
    // then point it at the short-lived signed URL (served inline, so the browser displays it).
    const tab = window.open("", "_blank");
    try {
      const { url } = await api<{ url: string; expires_in: number }>(
        `/documents/${documentId}/url?disposition=inline`,
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

  async function onDownload(documentId: string) {
    setActionError(null);
    try {
      const { url } = await api<{ url: string; expires_in: number }>(
        `/documents/${documentId}/url?disposition=attachment`,
      );
      window.location.assign(url); // Content-Disposition: attachment, so the page stays put
    } catch (err) {
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

  async function changeStatus(status: string, extra: Record<string, unknown> = {}) {
    setBusy(true);
    setActionError(null);
    try {
      const updated = await api<ApplicationDetail>(`/applications/${app.id}/status`, {
        method: "PATCH",
        body: JSON.stringify({ status, ...extra }),
      });
      setState({ kind: "ready", app: updated });
      setConfirmSubmit(false);
      setRejectOpen(false);
      setRejectNote("");
      setApproveOpen(false);
      setApproveNote("");
      setDeficientOpen(false);
      setDeficientNote("");
      setScheduleOpen(false);
    } catch (err) {
      setActionError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function startInspection() {
    setBusy(true);
    setActionError(null);
    try {
      const updated = await api<ApplicationDetail>(`/applications/${app.id}/status`, {
        method: "PATCH",
        body: JSON.stringify({ status: "INSPECTION" }),
      });
      // No dialog: unlike Schedule, there is nothing to confirm, just enter the field flow.
      if (updated.inspection) router.push(`/inspections/${updated.inspection.id}`);
    } catch (err) {
      setActionError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function issueCertificate() {
    setBusy(true);
    setActionError(null);
    try {
      const updated = await api<ApplicationDetail>(`/applications/${app.id}/certificate`, {
        method: "POST",
      });
      setState({ kind: "ready", app: updated });
    } catch (err) {
      setActionError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function reschedule(newDate: string) {
    setBusy(true);
    setActionError(null);
    try {
      const updated = await api<ApplicationDetail>(`/applications/${app.id}/inspection`, {
        method: "PATCH",
        body: JSON.stringify({ scheduled_date: newDate }),
      });
      setState({ kind: "ready", app: updated });
    } catch (err) {
      setActionError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  // Step 11: each checkbox fires its own single-item PATCH (the endpoint's `items` array accepts
  // a partial batch, but a per-toggle call keeps each checkbox's own pending/error state simple
  // and matches this page's existing one-action-one-request pattern, e.g. onDeleteDocument).
  async function toggleReviewItem(itemKey: string, checked: boolean) {
    setReviewBusy(itemKey);
    setActionError(null);
    try {
      const updated = await api<ApplicationDetail>(`/applications/${app.id}/review-checklist`, {
        method: "PATCH",
        body: JSON.stringify({ items: [{ item_key: itemKey, checked }] }),
      });
      setState({ kind: "ready", app: updated });
    } catch (err) {
      setActionError(errorMessage(err));
    } finally {
      setReviewBusy(null);
    }
  }

  // Spec 12: purely informational — never implies this gates any other step.
  async function onMockPay() {
    setPayBusy(true);
    setActionError(null);
    try {
      const updated = await api<ApplicationDetail>(`/applications/${app.id}/mock-pay`, {
        method: "POST",
      });
      setState({ kind: "ready", app: updated });
    } catch (err) {
      setActionError(errorMessage(err));
    } finally {
      setPayBusy(false);
    }
  }

  // Spec 15: opening the Schedule dialog decides whether to offer GATC routing at all. Only an
  // OFFICE_TEST_CENTRE application with a category-tagged instrument ever triggers the extra
  // fetches; an ON_SITE application (or one with no category_id) leaves gatcEligible `null` and
  // the dialog renders exactly as it did before this step.
  async function openSchedule() {
    setScheduleOpen(true);
    setGatcMode("self");
    setGatcEligible(null);
    setGatcOrgId("");
    setGatcUsers(null);
    setGatcUserId("");
    if (app.verification_mode !== "OFFICE_TEST_CENTRE") return;
    setGatcLoading(true);
    try {
      const instrument = await api<Instrument>(`/instruments/${app.instrument.id}`);
      if (instrument.category_id !== null) {
        setGatcEligible(await getGatcEligible(instrument.category_id));
      } else {
        setGatcEligible([]); // checked, but no category to route on -> self-assign only
      }
    } catch {
      setGatcEligible([]); // fail closed: self-assign always still works
    } finally {
      setGatcLoading(false);
    }
  }

  async function onSelectGatcOrg(orgId: string) {
    setGatcOrgId(orgId);
    setGatcUserId("");
    setGatcUsers(null);
    if (!orgId) return;
    try {
      setGatcUsers(await getGatcOrgUsers(orgId));
    } catch {
      setGatcUsers([]);
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
          {app.verification_mode ? (
            <p className="text-sm text-muted-foreground">
              Verification mode: {labelFor(meta?.verification_modes, app.verification_mode)}
            </p>
          ) : null}
        </div>
        <StatusBadge status={app.status} label={labelFor(meta?.statuses, app.status)} />
      </div>

      {actionError ? (
        <Alert variant="destructive">
          <AlertDescription>{actionError}</AlertDescription>
        </Alert>
      ) : null}

      {deficiencyNote ? (
        <Alert>
          <AlertDescription>
            <span className="font-medium">Documents deficient — </span>
            {deficiencyNote}
          </AlertDescription>
        </Alert>
      ) : null}

      {/* Actions come from allowed_actions: the UI never guesses permissions.
          Exception: Issue certificate (canIssueCertificate), see its definition above. */}
      {app.allowed_actions.length > 0 || canIssueCertificate ? (
        <div className="flex flex-wrap gap-2">
          {canSubmit ? (
            <Button onClick={() => setConfirmSubmit(true)} disabled={!requirementsMet || busy}>
              {app.status === "DOCUMENTS_DEFICIENT" ? "Resubmit application" : "Submit application"}
            </Button>
          ) : null}
          {app.allowed_actions.includes("DOCUMENT_REVIEW") ? (
            <Button onClick={() => void changeStatus("DOCUMENT_REVIEW")} disabled={busy}>
              {busy ? "Starting…" : "Start review"}
            </Button>
          ) : null}
          {app.allowed_actions.includes("APPROVED") ? (
            <Button onClick={() => setApproveOpen(true)} disabled={busy}>
              Approve
            </Button>
          ) : null}
          {app.allowed_actions.includes("DOCUMENTS_DEFICIENT") ? (
            <Button variant="outline" onClick={() => setDeficientOpen(true)} disabled={busy}>
              Send back (documents deficient)
            </Button>
          ) : null}
          {app.allowed_actions.includes("REJECTED") ? (
            <Button variant="destructive" onClick={() => setRejectOpen(true)} disabled={busy}>
              Reject
            </Button>
          ) : null}
          {canSchedule ? (
            <Button
              onClick={() => void openSchedule()}
              disabled={busy || !reviewChecklistComplete}
              title={!reviewChecklistComplete ? "Complete the document review checklist first" : undefined}
            >
              Schedule inspection
            </Button>
          ) : null}
          {canStartInspection ? (
            <Button onClick={() => void startInspection()} disabled={busy}>
              {busy ? "Starting…" : "Start inspection"}
            </Button>
          ) : null}
          {canIssueCertificate ? (
            <Button onClick={() => void issueCertificate()} disabled={busy}>
              {busy ? "Issuing…" : "Issue certificate"}
            </Button>
          ) : null}
        </div>
      ) : null}
      {canSubmit && !requirementsMet ? (
        <p className="-mt-3 text-sm text-muted-foreground">Upload every required document to submit.</p>
      ) : null}
      {canSchedule && !reviewChecklistComplete ? (
        <p className="-mt-3 text-sm text-muted-foreground">
          Check off every document review item before scheduling.
        </p>
      ) : null}

      {app.review_checklist.length > 0 ? (
        <section className="grid gap-3 rounded-lg border p-4">
          <h2 className="text-lg font-medium">Document review checklist</h2>
          {app.status === "DOCUMENT_REVIEW" && isOfficer ? (
            <ul className="grid gap-2">
              {app.review_checklist.map((item) => (
                <li key={item.item_key}>
                  <Label
                    htmlFor={`review_${item.item_key}`}
                    className="flex min-h-9 items-start gap-2 font-normal"
                  >
                    <Checkbox
                      id={`review_${item.item_key}`}
                      checked={item.checked}
                      disabled={reviewBusy !== null}
                      onCheckedChange={(next) => void toggleReviewItem(item.item_key, next === true)}
                    />
                    <span>{item.label}</span>
                  </Label>
                </li>
              ))}
            </ul>
          ) : (
            // Read-only display for BUSINESS/other viewers, or once past DOCUMENT_REVIEW.
            <ul className="grid gap-1 text-sm">
              {app.review_checklist.map((item) => (
                <li key={item.item_key}>
                  {item.checked ? "✓" : "•"} {item.label}
                </li>
              ))}
            </ul>
          )}
        </section>
      ) : null}

      {app.inspection ? (
        <section className="grid gap-2 rounded-lg border p-4">
          <p className="text-sm font-medium">
            Scheduled for {new Date(app.inspection.scheduled_date).toLocaleDateString()}
          </p>
          <p className="text-sm text-muted-foreground">
            Assigned to {app.inspection.assigned_officer_name} (
            {assigneeRoleLabel(app.inspection.assignee_role)})
          </p>
          {app.inspection.submitted_at && app.inspection.checklist_summary ? (
            <p className="text-sm text-muted-foreground">
              Checklist: {app.inspection.checklist_summary.passed} passed,{" "}
              {app.inspection.checklist_summary.failed} failed, {app.inspection.checklist_summary.na}{" "}
              n/a
            </p>
          ) : null}
          {app.status === "INSPECTION" && isOfficer ? (
            <Button
              variant="outline"
              size="sm"
              className="w-fit"
              onClick={() => router.push(`/inspections/${app.inspection!.id}`)}
            >
              {app.inspection.submitted_at ? "View inspection" : "Continue inspection"}
            </Button>
          ) : null}
          {app.can_reschedule ? (
            <div className="flex flex-wrap items-end gap-2">
              <div className="grid gap-1.5">
                <Label htmlFor="reschedule_date">Change date</Label>
                <Input
                  id="reschedule_date"
                  type="date"
                  className="w-auto"
                  value={rescheduleDate}
                  min={minScheduleDate}
                  max={maxScheduleDate}
                  onChange={(e) => setRescheduleDate(e.target.value)}
                />
              </div>
              <Button
                variant="outline"
                size="sm"
                onClick={() => void reschedule(rescheduleDate)}
                disabled={busy || !rescheduleDate || rescheduleDate === app.inspection.scheduled_date}
              >
                {busy ? "Saving…" : "Save"}
              </Button>
            </div>
          ) : null}
        </section>
      ) : null}

      {app.certificate ? (
        <section className="grid gap-2 rounded-lg border p-4">
          <p className="text-sm font-medium">{app.certificate.certificate_number}</p>
          <p className="text-sm text-muted-foreground">
            Valid {new Date(app.certificate.valid_from).toLocaleDateString()} –{" "}
            {new Date(app.certificate.valid_until).toLocaleDateString()}
          </p>
          {app.certificate.is_expiring_soon ? (
            <p className="text-sm font-medium text-amber-600 dark:text-amber-500">
              Expiring soon — a re-verification may be needed shortly.
            </p>
          ) : null}
          {app.certificate.superseded_by_certificate_id ? (
            <p className="text-sm text-muted-foreground">
              This certificate has been superseded by a newer one.
            </p>
          ) : null}
          {app.certificate.supersedes_certificate_id ? (
            <p className="text-sm text-muted-foreground">Supersedes an earlier certificate.</p>
          ) : null}
          <Link href={`/certificates/${app.certificate.id}`} className="w-fit">
            <Button variant="outline" size="sm">
              View certificate
            </Button>
          </Link>
        </section>
      ) : null}

      <section className="grid gap-2 rounded-lg border p-4">
        <h2 className="text-sm font-medium">Payment</h2>
        <p className="text-sm text-muted-foreground">
          {labelFor(meta?.payment_statuses, app.payment?.status ?? "NOT_PAID")}
          {app.payment?.paid_at ? ` · ${new Date(app.payment.paid_at).toLocaleDateString()}` : ""}
        </p>
        <p className="text-xs text-muted-foreground">
          Informational only (prototype) — payment status doesn&apos;t affect any other step of this
          application.
        </p>
        {isOwner && (!app.payment || app.payment.status !== "PAID") ? (
          <Button
            variant="outline"
            size="sm"
            className="w-fit"
            onClick={() => void onMockPay()}
            disabled={payBusy}
          >
            {payBusy ? "Processing…" : "Mock pay (prototype)"}
          </Button>
        ) : null}
      </section>

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
                          <Button variant="ghost" size="sm" onClick={() => void onDownload(d.id)}>
                            Download
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
            <DialogTitle>
              {app.status === "DOCUMENTS_DEFICIENT" ? "Resubmit this application?" : "Submit this application?"}
            </DialogTitle>
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
              onClick={() => void changeStatus("REJECTED", { note: rejectNote.trim() })}
              disabled={busy || rejectNote.trim().length < REJECT_MIN}
            >
              {busy ? "Rejecting…" : "Reject"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={approveOpen} onOpenChange={setApproveOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Approve this application?</DialogTitle>
            <DialogDescription>
              The instrument stays location-locked until the certificate is issued.
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-1.5">
            <Label htmlFor="approve_note">Note (optional)</Label>
            <Textarea
              id="approve_note"
              value={approveNote}
              maxLength={1000}
              onChange={(e) => setApproveNote(e.target.value)}
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setApproveOpen(false)} disabled={busy}>
              Cancel
            </Button>
            <Button
              onClick={() =>
                void changeStatus("APPROVED", approveNote.trim() ? { note: approveNote.trim() } : {})
              }
              disabled={busy}
            >
              {busy ? "Approving…" : "Approve"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={deficientOpen} onOpenChange={setDeficientOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Send back as documents deficient?</DialogTitle>
            <DialogDescription>
              This doesn&apos;t reject the application — the business can fix the issue and resubmit.
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-1.5">
            <Label htmlFor="deficient_note">What&apos;s missing or wrong</Label>
            <Textarea
              id="deficient_note"
              value={deficientNote}
              maxLength={1000}
              onChange={(e) => setDeficientNote(e.target.value)}
            />
            <p className="text-xs text-muted-foreground">At least {DEFICIENCY_MIN} characters.</p>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeficientOpen(false)} disabled={busy}>
              Cancel
            </Button>
            <Button
              onClick={() => void changeStatus("DOCUMENTS_DEFICIENT", { note: deficientNote.trim() })}
              disabled={busy || deficientNote.trim().length < DEFICIENCY_MIN}
            >
              {busy ? "Sending…" : "Send back"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={scheduleOpen} onOpenChange={setScheduleOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Schedule the inspection?</DialogTitle>
            <DialogDescription>
              The instrument&apos;s address and coordinates will be locked until the application is
              completed or rejected.
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-1.5">
            <Label htmlFor="schedule_date">Date</Label>
            <Input
              id="schedule_date"
              type="date"
              value={scheduleDate}
              min={minScheduleDate}
              max={maxScheduleDate}
              onChange={(e) => setScheduleDate(e.target.value)}
            />
          </div>

          {/* Spec 15: GATC routing. Only ever shown for an OFFICE_TEST_CENTRE, category-tagged
              application with at least one eligible GATC organization — an ON_SITE application
              (or one with no category_id) renders none of this, self-assign-only, unchanged. */}
          {gatcLoading ? (
            <p className="text-sm text-muted-foreground">Checking for eligible GATC test centres…</p>
          ) : gatcEligible && gatcEligible.length > 0 ? (
            <div className="grid gap-3">
              <div className="grid gap-1.5">
                <Label>Assign to</Label>
                <div className="flex gap-2">
                  <Button
                    type="button"
                    size="sm"
                    variant={gatcMode === "self" ? "default" : "outline"}
                    onClick={() => setGatcMode("self")}
                  >
                    Myself (self-assign)
                  </Button>
                  <Button
                    type="button"
                    size="sm"
                    variant={gatcMode === "gatc" ? "default" : "outline"}
                    onClick={() => setGatcMode("gatc")}
                  >
                    Route to a GATC test centre
                  </Button>
                </div>
              </div>
              {gatcMode === "gatc" ? (
                <>
                  <SelectField
                    name="gatc_org"
                    label="GATC test centre"
                    value={gatcOrgId}
                    options={gatcEligible.map((o) => ({
                      value: o.id,
                      label: `${o.name} (${o.district_code}, ${o.state_code})`,
                    }))}
                    onChange={(v) => void onSelectGatcOrg(v)}
                  />
                  {gatcOrgId ? (
                    <SelectField
                      name="gatc_user"
                      label="Staff member"
                      value={gatcUserId}
                      options={(gatcUsers ?? []).map((u) => ({
                        value: u.id,
                        label: `${u.full_name} (${u.email})`,
                      }))}
                      onChange={setGatcUserId}
                      placeholder={gatcUsers === null ? "Loading…" : "Select…"}
                    />
                  ) : null}
                </>
              ) : null}
            </div>
          ) : gatcEligible !== null ? (
            <p className="text-sm text-muted-foreground">
              No eligible GATC test centre is configured for this instrument&apos;s category — this
              inspection will be self-assigned.
            </p>
          ) : null}

          <DialogFooter>
            <Button variant="outline" onClick={() => setScheduleOpen(false)} disabled={busy}>
              Cancel
            </Button>
            <Button
              onClick={() =>
                void changeStatus("SCHEDULED", {
                  scheduled_date: scheduleDate,
                  ...(gatcMode === "gatc" && gatcOrgId && gatcUserId
                    ? { gatc_organization_id: gatcOrgId, gatc_user_id: gatcUserId }
                    : {}),
                })
              }
              disabled={busy || !scheduleDate || (gatcMode === "gatc" && (!gatcOrgId || !gatcUserId))}
            >
              {busy ? "Scheduling…" : "Schedule"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
