"use client";

import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState, type ChangeEvent } from "react";

import { CheckCircle2, MinusCircle, XCircle } from "lucide-react";
import { cn } from "cn";

import { NO_ACCESS, StateMessage } from "@/components/instruments/state-message";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
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
import { ApiError, api, getInspection, patchInspection, submitInspection, uploadDocument } from "@/lib/api";
import { getApplicationMeta, labelFor } from "@/lib/meta";
import { assigneeRoleLabel } from "@/lib/utils";
import type {
  ApplicationDetail,
  ApplicationMeta,
  ChecklistResult,
  DocumentOut,
  InspectionDetail,
} from "@/lib/types";

type ChecklistDraft = Record<string, { result: string; remarks: string }>;
type MeasurementDraft = Record<string, string>;

type ReadyState = {
  kind: "ready";
  inspection: InspectionDetail;
  app: ApplicationDetail;
  results: ChecklistDraft;
  observed: MeasurementDraft;
  overallRemarks: string;
};

type State =
  | { kind: "loading" }
  | { kind: "not-found" }
  | { kind: "forbidden" }
  | { kind: "error" }
  | ReadyState;

function draftFrom(inspection: InspectionDetail): Pick<ReadyState, "results" | "observed" | "overallRemarks"> {
  return {
    results: Object.fromEntries(
      inspection.checklist_items.map((i) => [i.item_key, { result: i.result ?? "", remarks: i.remarks ?? "" }]),
    ),
    observed: Object.fromEntries(
      inspection.measurements.map((m) => [m.label, m.observed_value?.toString() ?? ""]),
    ),
    overallRemarks: inspection.overall_remarks ?? "",
  };
}

const STEPS = ["instrument", "checklist", "measurements", "photos", "remarks", "submit"] as const;
type Step = (typeof STEPS)[number];
const STEP_LABELS: Record<Step, string> = {
  instrument: "Instrument details",
  checklist: "Checklist",
  measurements: "Measurements",
  photos: "Evidence",
  remarks: "Remarks",
  submit: "Submit",
};

// Icon + label per result so status is never color-only (CLAUDE.md a11y bar).
const RESULT_META: Record<ChecklistResult, { label: string; icon: typeof CheckCircle2 }> = {
  PASS: { label: "Pass", icon: CheckCircle2 },
  FAIL: { label: "Fail", icon: XCircle },
  NA: { label: "N/A", icon: MinusCircle },
};

function errorMessage(err: unknown): string {
  if (!(err instanceof ApiError)) return "Could not reach the server.";
  const fieldMessage = Object.values(err.fieldErrors)[0];
  return fieldMessage ?? err.message;
}

// Three large, tappable buttons (44px+) instead of a dropdown — each carries its own icon and
// label, so the selected result is never conveyed by color alone.
function ChecklistResultToggle({
  itemKey,
  value,
  disabled,
  onChange,
}: {
  itemKey: string;
  value: string;
  disabled: boolean;
  onChange: (value: ChecklistResult) => void;
}) {
  return (
    <div className="grid grid-cols-3 gap-2" role="group" aria-label="Result">
      {(Object.keys(RESULT_META) as ChecklistResult[]).map((result) => {
        const { label, icon: Icon } = RESULT_META[result];
        const selected = value === result;
        return (
          <button
            key={result}
            type="button"
            id={`result-${itemKey}-${result}`}
            aria-pressed={selected}
            disabled={disabled}
            onClick={() => onChange(result)}
            className={cn(
              "flex min-h-11 flex-col items-center justify-center gap-1 rounded-lg border px-2 py-2 text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-ring/50 disabled:pointer-events-none disabled:opacity-50",
              !selected && "border-border bg-background text-muted-foreground hover:bg-muted",
              selected &&
                result === "PASS" &&
                "border-success bg-success/10 text-success",
              selected && result === "FAIL" && "border-destructive bg-destructive/10 text-destructive",
              selected && result === "NA" && "border-foreground/40 bg-muted text-foreground",
            )}
          >
            <Icon className="size-5" aria-hidden="true" />
            {label}
          </button>
        );
      })}
    </div>
  );
}

export default function InspectionPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [state, setState] = useState<State>({ kind: "loading" });
  const [meta, setMeta] = useState<ApplicationMeta | null>(null);
  const [stepIndex, setStepIndex] = useState(0);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [confirmSubmit, setConfirmSubmit] = useState(false);

  const load = useCallback(async () => {
    try {
      const inspection = await getInspection(id);
      const app = await api<ApplicationDetail>(`/applications/${inspection.application_id}`);
      setState({ kind: "ready", inspection, app, ...draftFrom(inspection) });
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) setState({ kind: "not-found" });
      else if (err instanceof ApiError && err.status === 403) setState({ kind: "forbidden" });
      else setState({ kind: "error" });
    }
  }, [id]);

  useEffect(() => {
    getApplicationMeta().then(setMeta, () => undefined);
    // Same fire-and-forget load-on-mount pattern as app/applications/[id]/page.tsx (which the
    // linter accepts); react-hooks/set-state-in-effect flags this one regardless, apparently
    // sensitive to load()'s two sequential awaits (inspection, then its application) in a way
    // that isn't a real synchronous setState-in-effect (confirmed by bisection against the
    // otherwise-identical, lint-clean pattern in that file).
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void load();
  }, [load]);

  if (state.kind === "loading") return <p className="text-sm text-muted-foreground">Loading…</p>;
  if (state.kind === "not-found") return <StateMessage title="Inspection not found" />;
  if (state.kind === "forbidden") return <StateMessage title={NO_ACCESS} />;
  if (state.kind === "error") return <StateMessage title="Could not load this inspection." />;

  const { inspection, app, results, observed, overallRemarks } = state;
  const canEdit = inspection.can_edit;
  const step = STEPS[stepIndex];
  // Spec 15: assignee_role isn't on InspectionDetail itself (GET /inspections/{id}) — it lives on
  // the lighter Inspection summary already embedded in ApplicationDetail.inspection, which this
  // page fetches anyway right after the inspection. Reused from there instead of duplicating it
  // onto InspectionDetail server-side just for display.
  const assigneeRole = app.inspection?.assignee_role;

  function updateReady(patch: Partial<Pick<ReadyState, "results" | "observed" | "overallRemarks">>) {
    setState((prev) => (prev.kind === "ready" ? { ...prev, ...patch } : prev));
  }

  function setChecklistField(itemKey: string, field: "result" | "remarks", value: string) {
    updateReady({
      results: { ...results, [itemKey]: { ...results[itemKey], [field]: value } },
    });
  }

  function setObservedValue(label: string, value: string) {
    updateReady({ observed: { ...observed, [label]: value } });
  }

  async function saveChecklist() {
    setSaving(true);
    setError(null);
    try {
      const updated = await patchInspection(inspection.id, {
        checklist_items: inspection.checklist_items.map((i) => ({
          item_key: i.item_key,
          result: results[i.item_key]?.result || null,
          remarks: results[i.item_key]?.remarks || null,
        })),
      });
      setState({ kind: "ready", inspection: updated, app, ...draftFrom(updated) });
      return true;
    } catch (err) {
      setError(errorMessage(err));
      return false;
    } finally {
      setSaving(false);
    }
  }

  async function saveMeasurements() {
    setSaving(true);
    setError(null);
    try {
      const updated = await patchInspection(inspection.id, {
        measurements: inspection.measurements.map((m) => ({
          label: m.label,
          observed_value: observed[m.label] || null,
        })),
      });
      setState({ kind: "ready", inspection: updated, app, ...draftFrom(updated) });
      return true;
    } catch (err) {
      setError(errorMessage(err));
      return false;
    } finally {
      setSaving(false);
    }
  }

  async function saveRemarks() {
    setSaving(true);
    setError(null);
    try {
      const updated = await patchInspection(inspection.id, { overall_remarks: overallRemarks || null });
      setState({ kind: "ready", inspection: updated, app, ...draftFrom(updated) });
      return true;
    } catch (err) {
      setError(errorMessage(err));
      return false;
    } finally {
      setSaving(false);
    }
  }

  async function goNext() {
    let ok = true;
    if (canEdit && step === "checklist") ok = await saveChecklist();
    if (canEdit && step === "measurements") ok = await saveMeasurements();
    if (canEdit && step === "remarks") ok = await saveRemarks();
    if (ok && stepIndex < STEPS.length - 1) setStepIndex(stepIndex + 1);
  }

  function goBack() {
    if (stepIndex > 0) setStepIndex(stepIndex - 1);
  }

  async function onPhoto(event: ChangeEvent<HTMLInputElement>) {
    const input = event.currentTarget;
    const file = input.files?.[0];
    input.value = "";
    if (!file) return;
    setUploadError(null);
    const limits = meta?.limits;
    if (limits && file.size > limits.max_file_bytes) {
      setUploadError("File is too large (maximum 10 MB)");
      return;
    }
    if (limits && file.type && !limits.allowed_content_types.includes(file.type)) {
      setUploadError("Only PDF, JPG and PNG files are allowed");
      return;
    }
    const form = new FormData();
    form.append("application_id", app.id);
    form.append("document_type", "INSPECTION_EVIDENCE");
    form.append("file", file);
    setUploading(true);
    try {
      await uploadDocument<DocumentOut>(form);
      await load();
    } catch (err) {
      setUploadError(errorMessage(err));
    } finally {
      setUploading(false);
    }
  }

  async function onDeletePhoto(documentId: string) {
    setUploadError(null);
    try {
      await api<void>(`/documents/${documentId}`, { method: "DELETE" });
      await load();
    } catch (err) {
      setUploadError(errorMessage(err));
    }
  }

  async function onSubmit() {
    setSaving(true);
    setError(null);
    try {
      await submitInspection(inspection.id);
      router.push(`/applications/${app.id}`);
    } catch (err) {
      setError(errorMessage(err));
      setConfirmSubmit(false);
    } finally {
      setSaving(false);
    }
  }

  const answeredCount = inspection.checklist_items.filter(
    (i) => (results[i.item_key]?.result || i.result) != null && (results[i.item_key]?.result || i.result) !== "",
  ).length;
  const measuredCount = inspection.measurements.filter(
    (m) => (observed[m.label] || "") !== "",
  ).length;
  const canReachSubmit =
    answeredCount === inspection.checklist_items.length &&
    measuredCount === inspection.measurements.length;

  const isFirst = stepIndex === 0;
  const isLast = step === "submit";

  return (
    <div className="mx-auto grid max-w-md gap-4 pb-28 sm:pb-4">
      <div className="grid gap-1">
        <span className="font-mono text-sm text-muted-foreground">{app.application_number}</span>
        <h1 className="text-xl font-semibold">Field inspection</h1>
        {inspection.assigned_officer_name ? (
          <p className="text-sm text-muted-foreground">
            Assigned to {inspection.assigned_officer_name}
            {assigneeRole ? (
              <>
                {" "}
                <Badge variant="outline" className="align-middle">
                  {assigneeRoleLabel(assigneeRole)}
                </Badge>
              </>
            ) : null}
          </p>
        ) : null}
      </div>

      {/* Tappable step indicator — one section visible at a time, but any step (already visited
          or not) can be jumped to directly, matching the donor prototype's pill tab bar. */}
      <ol className="flex flex-wrap gap-2" aria-label="Inspection sections">
        {STEPS.map((s, i) => {
          const isCurrent = i === stepIndex;
          const isDone = i < stepIndex;
          return (
            <li key={s}>
              <button
                type="button"
                onClick={() => setStepIndex(i)}
                aria-current={isCurrent ? "step" : undefined}
                className={cn(
                  "min-h-9 rounded-full border px-3 py-1 text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-ring/50",
                  isCurrent && "border-primary bg-primary text-primary-foreground",
                  !isCurrent && isDone && "border-success/40 bg-success/10 text-success",
                  !isCurrent && !isDone && "border-border bg-background text-muted-foreground",
                )}
              >
                {i + 1}. {STEP_LABELS[s]}
              </button>
            </li>
          );
        })}
      </ol>

      {!canEdit ? (
        <Alert>
          <AlertDescription>
            {inspection.submitted_at
              ? "This inspection has been submitted and is read-only."
              : "You can view this inspection, but only the assigned officer can edit it."}
          </AlertDescription>
        </Alert>
      ) : null}

      {error ? (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle>{STEP_LABELS[step]}</CardTitle>
        </CardHeader>
        <CardContent>
          {step === "instrument" ? (
            <section className="grid gap-2">
              <p className="font-medium">{app.instrument.instrument_uid}</p>
              <p className="text-sm text-muted-foreground">
                {app.instrument.manufacturer} {app.instrument.model} · S/N {app.instrument.serial_number}
              </p>
              <p className="text-sm text-muted-foreground">
                Capacity {app.instrument.capacity} {app.instrument.capacity_unit}
              </p>
              <p className="text-sm text-muted-foreground">
                Location {app.state_code} / {app.district_code}
                {app.verification_mode
                  ? ` · ${labelFor(meta?.verification_modes, app.verification_mode)}`
                  : null}
              </p>
              <p className="text-sm text-muted-foreground">
                Scheduled for {new Date(inspection.scheduled_date).toLocaleDateString()} · Assigned to{" "}
                {inspection.assigned_officer_name}
              </p>
            </section>
          ) : null}

          {step === "checklist" ? (
            <section className="grid gap-4">
              {inspection.checklist_items.map((item) => (
                <div key={item.item_key} className="grid gap-2 rounded-lg border p-4">
                  <p className="font-medium">{item.label}</p>
                  <ChecklistResultToggle
                    itemKey={item.item_key}
                    value={results[item.item_key]?.result ?? ""}
                    disabled={!canEdit}
                    onChange={(v) => setChecklistField(item.item_key, "result", v)}
                  />
                  <div className="grid gap-1.5">
                    <Label htmlFor={`remarks-${item.item_key}`}>Remarks (optional)</Label>
                    <Textarea
                      id={`remarks-${item.item_key}`}
                      value={results[item.item_key]?.remarks ?? ""}
                      disabled={!canEdit}
                      onChange={(e) => setChecklistField(item.item_key, "remarks", e.target.value)}
                    />
                  </div>
                </div>
              ))}
            </section>
          ) : null}

          {step === "measurements" ? (
            <section className="grid gap-4">
              {inspection.measurements.map((m) => (
                <div key={m.label} className="grid gap-2 rounded-lg border p-4">
                  <p className="font-medium">{m.label}</p>
                  <p className="text-sm text-muted-foreground">
                    Expected {m.expected_value} {m.unit}
                  </p>
                  <div className="grid gap-1.5">
                    <Label htmlFor={`observed-${m.label}`}>Observed value ({m.unit})</Label>
                    <input
                      id={`observed-${m.label}`}
                      className="h-11 rounded-lg border px-3 text-sm focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-ring/50"
                      inputMode="decimal"
                      value={observed[m.label] ?? ""}
                      disabled={!canEdit}
                      onChange={(e) => setObservedValue(m.label, e.target.value)}
                    />
                  </div>
                </div>
              ))}
            </section>
          ) : null}

          {step === "photos" ? (
            <section className="grid gap-3">
              {canEdit ? (
                <Label
                  className={cn(
                    "flex min-h-11 w-fit items-center rounded-md border px-4 text-sm",
                    uploading ? "pointer-events-none opacity-50" : "cursor-pointer hover:bg-muted",
                  )}
                >
                  {uploading ? "Uploading…" : "Add photo"}
                  <input
                    type="file"
                    accept="image/*"
                    capture="environment"
                    className="sr-only"
                    disabled={uploading}
                    onChange={(e) => void onPhoto(e)}
                  />
                </Label>
              ) : null}
              {uploadError ? <p className="text-sm text-destructive">{uploadError}</p> : null}
              {inspection.evidence.length === 0 ? (
                <p className="text-sm text-muted-foreground">No photos yet.</p>
              ) : (
                <ul className="grid gap-2">
                  {inspection.evidence.map((d) => (
                    <li
                      key={d.id}
                      className="flex min-h-11 items-center justify-between gap-2 rounded-lg border p-3 text-sm"
                    >
                      <span className="break-all">{d.original_filename}</span>
                      {canEdit ? (
                        <Button
                          variant="ghost"
                          className="min-h-9"
                          onClick={() => void onDeletePhoto(d.id)}
                        >
                          Remove
                        </Button>
                      ) : null}
                    </li>
                  ))}
                </ul>
              )}
            </section>
          ) : null}

          {step === "remarks" ? (
            <section className="grid gap-1.5">
              <Label htmlFor="overall_remarks">Overall remarks (optional)</Label>
              <Textarea
                id="overall_remarks"
                value={overallRemarks}
                disabled={!canEdit}
                onChange={(e) => updateReady({ overallRemarks: e.target.value })}
              />
            </section>
          ) : null}

          {step === "submit" ? (
            <section className="grid gap-3">
              <p className="text-sm">
                {answeredCount} of {inspection.checklist_items.length} checklist items answered ·{" "}
                {measuredCount} of {inspection.measurements.length} measurements recorded ·{" "}
                {inspection.evidence.length} photo(s)
              </p>
              {!canReachSubmit ? (
                <p className="text-sm text-destructive">
                  Complete every checklist item and measurement before submitting.
                </p>
              ) : null}
              {inspection.submitted_at ? (
                <p className="text-sm text-muted-foreground">
                  Submitted {new Date(inspection.submitted_at).toLocaleString()}.
                </p>
              ) : canEdit ? (
                <Button className="min-h-11" onClick={() => setConfirmSubmit(true)} disabled={!canReachSubmit || saving}>
                  Submit inspection
                </Button>
              ) : null}
            </section>
          ) : null}
        </CardContent>
      </Card>

      {/* Sticky on mobile so Back/Next stay reachable one-handed; becomes an inline row once
          there's room (sm:), matching the donor prototype's breakpoint. */}
      <div className="fixed inset-x-0 bottom-0 z-10 mx-auto flex max-w-md items-center justify-between gap-2 border-t bg-background p-3 sm:static sm:border-0 sm:bg-transparent sm:p-0">
        <Button
          variant="outline"
          className="min-h-11 flex-1 sm:flex-none"
          onClick={goBack}
          disabled={isFirst || saving}
        >
          Back
        </Button>
        {!isLast ? (
          <Button className="min-h-11 flex-1 sm:flex-none" onClick={() => void goNext()} disabled={saving}>
            {saving ? "Saving…" : `Next: ${STEP_LABELS[STEPS[stepIndex + 1]]}`}
          </Button>
        ) : null}
      </div>

      <Dialog open={confirmSubmit} onOpenChange={setConfirmSubmit}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Submit this inspection?</DialogTitle>
            <DialogDescription>
              After submitting, the checklist, measurements and photos can no longer be changed.
              Approving or rejecting the application happens separately.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" className="min-h-11" onClick={() => setConfirmSubmit(false)} disabled={saving}>
              Cancel
            </Button>
            <Button className="min-h-11" onClick={() => void onSubmit()} disabled={saving}>
              {saving ? "Submitting…" : "Submit"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
