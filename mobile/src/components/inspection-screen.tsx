import type { ApplicationDetail, ChecklistResult, DocumentOut, InspectionDetail } from "@api-types";
import { router, useLocalSearchParams } from "expo-router";
import { useState } from "react";
import { Alert, Linking, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { Button, ErrorState, ErrorText, InfoText, Loading, Muted, TextField } from "@/components/ui";
import { ApiError, api, describeError } from "@/lib/api";
import { getApplicationMeta, getInspectionMeta, labelFor } from "@/lib/meta";
import { colors } from "@/lib/theme";
import { pickPhoto, uploadDocument } from "@/lib/upload";
import { useAsync } from "@/lib/use-async";
import { formatDate } from "@/lib/verify";

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

// Checklist results are a small backend-owned enum; icon + label so the result is never color-only.
const RESULTS: { value: ChecklistResult; label: string; icon: string }[] = [
  { value: "PASS", label: "Pass", icon: "✓" },
  { value: "FAIL", label: "Fail", icon: "✕" },
  { value: "NA", label: "N/A", icon: "–" },
];

type Draft = {
  results: Record<string, { result: string; remarks: string }>;
  observed: Record<string, string>;
  overallRemarks: string;
};

function draftFrom(i: InspectionDetail): Draft {
  return {
    results: Object.fromEntries(i.checklist_items.map((c) => [c.item_key, { result: c.result ?? "", remarks: c.remarks ?? "" }])),
    observed: Object.fromEntries(i.measurements.map((m) => [m.label, m.observed_value?.toString() ?? ""])),
    overallRemarks: i.overall_remarks ?? "",
  };
}

function errorMessage(err: unknown): string {
  if (err instanceof ApiError) return Object.values(err.fieldErrors)[0] ?? err.message;
  return describeError(err);
}

/** Loads the inspection and its application, then hands them to the step flow. */
export function InspectionScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const state = useAsync(async () => {
    const inspection = await api<InspectionDetail>(`/inspections/${id}`);
    const app = await api<ApplicationDetail>(`/applications/${inspection.application_id}`);
    return { inspection, app };
  });
  if (!state.data) {
    return state.status === "error" ? (
      <ErrorState message="This inspection wasn't found, or you can't access it." onRetry={state.retry} />
    ) : (
      <Loading />
    );
  }
  return <InspectionFlow key={state.data.inspection.id} initial={state.data.inspection} app={state.data.app} />;
}

function InspectionFlow({ initial, app }: { initial: InspectionDetail; app: ApplicationDetail }) {
  const [inspection, setInspection] = useState(initial);
  const [draft, setDraft] = useState<Draft>(() => draftFrom(initial));
  const [stepIndex, setStepIndex] = useState(0);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const appMeta = useAsync(getApplicationMeta);
  const inspMeta = useAsync(getInspectionMeta);

  const step = STEPS[stepIndex]!;
  const canEdit = inspection.can_edit;
  const assigneeRole = app.inspection?.assignee_role;
  const maxPhotos = inspMeta.data?.max_evidence_photos;

  async function patch(body: Record<string, unknown>): Promise<boolean> {
    setSaving(true);
    setError(null);
    try {
      const updated = await api<InspectionDetail>(`/inspections/${inspection.id}`, { method: "PATCH", body: JSON.stringify(body) });
      setInspection(updated);
      setDraft(draftFrom(updated));
      return true;
    } catch (err) {
      setError(errorMessage(err));
      return false;
    } finally {
      setSaving(false);
    }
  }

  // Each Next PATCHes that step before advancing, so a slow connection never loses input.
  async function goNext() {
    let ok = true;
    if (canEdit && step === "checklist") {
      ok = await patch({
        checklist_items: inspection.checklist_items.map((i) => ({
          item_key: i.item_key,
          result: draft.results[i.item_key]?.result || null,
          remarks: draft.results[i.item_key]?.remarks || null,
        })),
      });
    } else if (canEdit && step === "measurements") {
      ok = await patch({
        measurements: inspection.measurements.map((m) => ({ label: m.label, observed_value: draft.observed[m.label] || null })),
      });
    } else if (canEdit && step === "remarks") {
      ok = await patch({ overall_remarks: draft.overallRemarks || null });
    }
    if (ok && stepIndex < STEPS.length - 1) setStepIndex(stepIndex + 1);
  }

  async function refresh() {
    const updated = await api<InspectionDetail>(`/inspections/${inspection.id}`);
    setInspection(updated);
  }

  async function addPhoto(source: "camera" | "library") {
    setUploadError(null);
    setUploading(true);
    try {
      const file = await pickPhoto(source);
      if (!file) return;
      await uploadDocument(app.id, "INSPECTION_EVIDENCE", file);
      await refresh();
    } catch (err) {
      setUploadError(err instanceof Error && !(err instanceof ApiError) ? err.message : errorMessage(err));
    } finally {
      setUploading(false);
    }
  }

  function confirmRemove(doc: DocumentOut) {
    Alert.alert("Remove this photo?", doc.original_filename, [
      { text: "Cancel", style: "cancel" },
      {
        text: "Remove",
        style: "destructive",
        onPress: () => {
          void (async () => {
            setUploadError(null);
            try {
              await api<void>(`/documents/${doc.id}`, { method: "DELETE" });
              await refresh();
            } catch (err) {
              setUploadError(errorMessage(err));
            }
          })();
        },
      },
    ]);
  }

  async function viewPhoto(doc: DocumentOut) {
    try {
      const { url } = await api<{ url: string; expires_in: number }>(`/documents/${doc.id}/url?disposition=inline`);
      await Linking.openURL(url);
    } catch (err) {
      setUploadError(errorMessage(err));
    }
  }

  const answered = inspection.checklist_items.filter((i) => (draft.results[i.item_key]?.result || i.result) != null && (draft.results[i.item_key]?.result || i.result) !== "").length;
  const measured = inspection.measurements.filter((m) => (draft.observed[m.label] || "") !== "").length;
  const canReachSubmit = answered === inspection.checklist_items.length && measured === inspection.measurements.length;

  function confirmSubmit() {
    Alert.alert(
      "Submit this inspection?",
      "This can't be undone: the checklist is locked once submitted.",
      [
        { text: "Cancel", style: "cancel" },
        {
          text: "Submit",
          onPress: () => {
            void (async () => {
              setSaving(true);
              setError(null);
              try {
                await api<InspectionDetail>(`/inspections/${inspection.id}/submit`, { method: "POST" });
                router.back(); // back to the application, where Approve / Reject is available
              } catch (err) {
                setError(errorMessage(err));
              } finally {
                setSaving(false);
              }
            })();
          },
        },
      ],
    );
  }

  const isFirst = stepIndex === 0;
  const isLast = step === "submit";

  return (
    <SafeAreaView style={styles.screen} edges={["left", "right", "bottom"]}>
      <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
        <Muted>{app.application_number}</Muted>
        <Text style={styles.heading}>Field inspection</Text>
        <Muted>
          Assigned to {inspection.assigned_officer_name}
          {assigneeRole ? ` (${assigneeRole === "GATC" ? "GATC" : "LM Officer"})` : ""}
        </Muted>

        {/* Tappable step pills: one section at a time, any step can be jumped to. */}
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 8 }}>
          {STEPS.map((s, i) => (
            <Pressable
              key={s}
              onPress={() => setStepIndex(i)}
              style={[styles.pill, i === stepIndex && styles.pillCurrent, i < stepIndex && styles.pillDone]}
            >
              <Text style={[styles.pillText, i === stepIndex && { color: colors.primaryText }]}>
                {i + 1}. {STEP_LABELS[s]}
              </Text>
            </Pressable>
          ))}
        </ScrollView>

        {!canEdit ? (
          <InfoText>
            {inspection.submitted_at
              ? "This inspection has been submitted and is read-only."
              : "You can view this inspection, but only the assigned inspector can edit it."}
          </InfoText>
        ) : null}
        {error ? <ErrorText>{error}</ErrorText> : null}

        <Text style={styles.stepTitle}>{STEP_LABELS[step]}</Text>

        {step === "instrument" ? (
          <View style={styles.card}>
            <Text style={styles.strong}>{app.instrument.instrument_uid}</Text>
            <Muted>
              {app.instrument.manufacturer} {app.instrument.model} · S/N {app.instrument.serial_number}
            </Muted>
            <Muted>
              Capacity {app.instrument.capacity} {app.instrument.capacity_unit}
            </Muted>
            <Muted>
              Location {app.state_code} / {app.district_code}
              {app.verification_mode ? ` · ${labelFor(appMeta.data?.verification_modes, app.verification_mode)}` : ""}
            </Muted>
            <Muted>
              Scheduled for {formatDate(inspection.scheduled_date)} · {inspection.assigned_officer_name}
            </Muted>
          </View>
        ) : null}

        {step === "checklist"
          ? inspection.checklist_items.map((item) => (
              <View key={item.item_key} style={styles.card}>
                <Text style={styles.strong}>{item.label}</Text>
                <View style={{ flexDirection: "row", gap: 8 }}>
                  {RESULTS.map((r) => {
                    const selected = draft.results[item.item_key]?.result === r.value;
                    return (
                      <Pressable
                        key={r.value}
                        disabled={!canEdit}
                        accessibilityRole="button"
                        accessibilityState={{ selected }}
                        onPress={() =>
                          setDraft((d) => ({ ...d, results: { ...d.results, [item.item_key]: { ...d.results[item.item_key]!, result: r.value } } }))
                        }
                        style={[styles.resultBtn, selected && resultSelected(r.value), !canEdit && { opacity: 0.6 }]}
                      >
                        <Text style={[styles.resultIcon, selected && { color: colors.text }]}>{r.icon}</Text>
                        <Text style={[styles.resultLabel, selected && { color: colors.text }]}>{r.label}</Text>
                      </Pressable>
                    );
                  })}
                </View>
                <TextField
                  label="Remarks (optional)"
                  value={draft.results[item.item_key]?.remarks ?? ""}
                  editable={canEdit}
                  multiline
                  onChangeText={(v) =>
                    setDraft((d) => ({ ...d, results: { ...d.results, [item.item_key]: { ...d.results[item.item_key]!, remarks: v } } }))
                  }
                  style={{ minHeight: 64, textAlignVertical: "top", paddingTop: 12 }}
                />
              </View>
            ))
          : null}

        {step === "measurements"
          ? inspection.measurements.map((m) => (
              <View key={m.label} style={styles.card}>
                <Text style={styles.strong}>{m.label}</Text>
                <Muted>
                  Expected {m.expected_value} {m.unit}
                </Muted>
                <TextField
                  label={`Observed value (${m.unit})`}
                  value={draft.observed[m.label] ?? ""}
                  editable={canEdit}
                  keyboardType="decimal-pad"
                  onChangeText={(v) => setDraft((d) => ({ ...d, observed: { ...d.observed, [m.label]: v } }))}
                />
              </View>
            ))
          : null}

        {step === "photos" ? (
          <View style={{ gap: 10 }}>
            {canEdit ? (
              <View style={{ flexDirection: "row", gap: 8 }}>
                <View style={{ flex: 1 }}>
                  <Button label="Take photo" onPress={() => void addPhoto("camera")} loading={uploading} disabled={uploading || (maxPhotos !== undefined && inspection.evidence.length >= maxPhotos)} />
                </View>
                <View style={{ flex: 1 }}>
                  <Button label="Choose photo" variant="secondary" onPress={() => void addPhoto("library")} disabled={uploading || (maxPhotos !== undefined && inspection.evidence.length >= maxPhotos)} />
                </View>
              </View>
            ) : null}
            {maxPhotos !== undefined ? (
              <Muted>
                {inspection.evidence.length} of {maxPhotos} photos
              </Muted>
            ) : null}
            {uploadError ? <ErrorText>{uploadError}</ErrorText> : null}
            {inspection.evidence.length === 0 ? <Muted>No photos yet.</Muted> : null}
            {inspection.evidence.map((d) => (
              <View key={d.id} style={[styles.card, { flexDirection: "row", alignItems: "center", gap: 14 }]}>
                <Text style={{ flex: 1, color: colors.text }} numberOfLines={1}>
                  {d.original_filename}
                </Text>
                <Text style={styles.link} onPress={() => void viewPhoto(d)}>
                  View
                </Text>
                {canEdit ? (
                  <Text style={[styles.link, { color: colors.danger }]} onPress={() => confirmRemove(d)}>
                    Remove
                  </Text>
                ) : null}
              </View>
            ))}
          </View>
        ) : null}

        {step === "remarks" ? (
          <TextField
            label="Overall remarks (optional)"
            value={draft.overallRemarks}
            editable={canEdit}
            multiline
            maxLength={2000}
            onChangeText={(v) => setDraft((d) => ({ ...d, overallRemarks: v }))}
            style={{ minHeight: 120, textAlignVertical: "top", paddingTop: 12 }}
          />
        ) : null}

        {step === "submit" ? (
          <View style={{ gap: 10 }}>
            <Text style={{ color: colors.text }}>
              {answered} of {inspection.checklist_items.length} checklist items answered · {measured} of {inspection.measurements.length} measurements recorded ·{" "}
              {inspection.evidence.length} photo(s)
            </Text>
            {!canReachSubmit ? <ErrorText>Complete every checklist item and measurement before submitting.</ErrorText> : null}
            {inspection.submitted_at ? (
              <Muted>Submitted {new Date(inspection.submitted_at).toLocaleString()}.</Muted>
            ) : canEdit ? (
              <Button label="Submit inspection" onPress={confirmSubmit} disabled={!canReachSubmit || saving} loading={saving} />
            ) : null}
          </View>
        ) : null}
      </ScrollView>

      {/* Sticky bottom bar: one-handed Back / Next. */}
      <View style={styles.bar}>
        <View style={{ flex: 1 }}>
          <Button label="Back" variant="secondary" onPress={() => setStepIndex(stepIndex - 1)} disabled={isFirst || saving} />
        </View>
        {!isLast ? (
          <View style={{ flex: 2 }}>
            <Button label={`Next: ${STEP_LABELS[STEPS[stepIndex + 1]!]}`} onPress={() => void goNext()} loading={saving} />
          </View>
        ) : null}
      </View>
    </SafeAreaView>
  );
}

function resultSelected(value: ChecklistResult) {
  if (value === "PASS") return { borderColor: "#16a34a", backgroundColor: "#dcfce7" };
  if (value === "FAIL") return { borderColor: "#dc2626", backgroundColor: "#fee2e2" };
  return { borderColor: "#6b7280", backgroundColor: "#e5e7eb" };
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.background },
  content: { padding: 16, gap: 12 },
  heading: { fontSize: 22, fontWeight: "700", color: colors.text },
  stepTitle: { fontSize: 18, fontWeight: "700", color: colors.text, marginTop: 4 },
  card: { backgroundColor: colors.card, borderRadius: 12, padding: 14, gap: 10, borderWidth: 1, borderColor: colors.border },
  strong: { fontSize: 15, fontWeight: "600", color: colors.text },
  pill: { borderRadius: 999, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, paddingHorizontal: 12, paddingVertical: 8 },
  pillCurrent: { backgroundColor: colors.primary, borderColor: colors.primary },
  pillDone: { borderColor: "#86efac", backgroundColor: "#f0fdf4" },
  pillText: { fontSize: 12, fontWeight: "600", color: colors.muted },
  resultBtn: { flex: 1, minHeight: 56, borderRadius: 10, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, alignItems: "center", justifyContent: "center", gap: 2 },
  resultIcon: { fontSize: 18, color: colors.muted, fontWeight: "700" },
  resultLabel: { fontSize: 12, color: colors.muted, fontWeight: "600" },
  link: { color: colors.primary, fontWeight: "600", paddingVertical: 6 },
  bar: { flexDirection: "row", gap: 10, padding: 12, borderTopWidth: 1, borderTopColor: colors.border, backgroundColor: colors.card },
});
