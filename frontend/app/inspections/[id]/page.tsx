"use client";

import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState, type ChangeEvent } from "react";

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
import { SelectField } from "@/components/select-field";
import { Textarea } from "@/components/ui/textarea";
import { ApiError, api, getInspection, patchInspection, submitInspection, uploadDocument } from "@/lib/api";
import { getApplicationMeta } from "@/lib/meta";
import type { ApplicationDetail, ApplicationMeta, DocumentOut, InspectionDetail } from "@/lib/types";

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
  photos: "Photos",
  remarks: "Remarks",
  submit: "Submit",
};

const RESULT_OPTIONS = [
  { value: "PASS", label: "Pass" },
  { value: "FAIL", label: "Fail" },
  { value: "NA", label: "N/A" },
];

function errorMessage(err: unknown): string {
  if (!(err instanceof ApiError)) return "Could not reach the server.";
  const fieldMessage = Object.values(err.fieldErrors)[0];
  return fieldMessage ?? err.message;
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

  return (
    <div className="mx-auto grid max-w-md gap-4 pb-24">
      <div className="grid gap-1">
        <span className="font-mono text-sm text-muted-foreground">{app.application_number}</span>
        <h1 className="text-xl font-semibold">Field inspection</h1>
        <p className="text-sm text-muted-foreground">
          Step {stepIndex + 1} of {STEPS.length} · {STEP_LABELS[step]}
        </p>
      </div>

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

      {step === "instrument" ? (
        <section className="grid gap-2 rounded-lg border p-4">
          <p className="font-medium">{app.instrument.instrument_uid}</p>
          <p className="text-sm text-muted-foreground">
            {app.instrument.manufacturer} {app.instrument.model} · S/N {app.instrument.serial_number}
          </p>
          <p className="text-sm text-muted-foreground">
            Capacity {app.instrument.capacity} {app.instrument.capacity_unit}
          </p>
          <p className="text-sm text-muted-foreground">
            Scheduled for {new Date(inspection.scheduled_date).toLocaleDateString()} · Assigned to{" "}
            {inspection.assigned_officer_name}
          </p>
        </section>
      ) : null}

      {step === "checklist" ? (
        <section className="grid gap-3">
          {inspection.checklist_items.map((item) => (
            <div key={item.item_key} className="grid gap-2 rounded-lg border p-4">
              <p className="font-medium">{item.label}</p>
              <SelectField
                name={`result-${item.item_key}`}
                label="Result"
                value={results[item.item_key]?.result ?? ""}
                options={RESULT_OPTIONS}
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
        <section className="grid gap-3">
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
                  className="h-10 rounded-lg border px-3 text-sm"
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
              className={
                uploading
                  ? "pointer-events-none w-fit opacity-50"
                  : "w-fit cursor-pointer rounded-md border px-3 py-1.5 text-sm hover:bg-muted"
              }
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
                <li key={d.id} className="flex items-center justify-between gap-2 rounded-lg border p-3 text-sm">
                  <span className="break-all">{d.original_filename}</span>
                  {canEdit ? (
                    <Button variant="ghost" size="sm" onClick={() => void onDeletePhoto(d.id)}>
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
        <section className="grid gap-3 rounded-lg border p-4">
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
            <Button onClick={() => setConfirmSubmit(true)} disabled={!canReachSubmit || saving}>
              Submit inspection
            </Button>
          ) : null}
        </section>
      ) : null}

      <div className="fixed inset-x-0 bottom-0 mx-auto flex max-w-md items-center justify-between gap-2 border-t bg-background p-3">
        <Button variant="outline" onClick={goBack} disabled={stepIndex === 0 || saving}>
          Back
        </Button>
        {step !== "submit" ? (
          <Button onClick={() => void goNext()} disabled={saving}>
            {saving ? "Saving…" : "Next"}
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
            <Button variant="outline" onClick={() => setConfirmSubmit(false)} disabled={saving}>
              Cancel
            </Button>
            <Button onClick={() => void onSubmit()} disabled={saving}>
              {saving ? "Submitting…" : "Submit"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
