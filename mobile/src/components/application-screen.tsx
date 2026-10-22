import type { ApplicationDetail, DocumentOut } from "@api-types";
import { router, useLocalSearchParams } from "expo-router";
import { useState } from "react";
import { Alert, Linking, StyleSheet, Text, View } from "react-native";

import { ScheduleDialog } from "@/components/schedule-dialog";
import { StatusBadge } from "@/components/status-badge";
import { Button, ChoiceModal, ErrorState, ErrorText, InfoText, Loading, Muted, NoteDialog, Screen, Title } from "@/components/ui";
import { ApiError, api, describeError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { openInTab } from "@/lib/nav";
import { getApplicationMeta, labelFor } from "@/lib/meta";
import { colors } from "@/lib/theme";
import { pickPdf, pickPhoto, uploadDocument, type PickedFile } from "@/lib/upload";
import { useAsync } from "@/lib/use-async";

// Backend rule: reasons for send-back / reject are 10-1000 characters.
const NOTE_MIN = 10;

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(0)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

function formatDateTime(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleString(undefined, { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });
}

export function ApplicationScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const { user } = useAuth();
  const state = useAsync(() => api<ApplicationDetail>(`/applications/${id}`));
  const meta = useAsync(getApplicationMeta);
  const [override, setOverride] = useState<ApplicationDetail | null>(null);
  const [uploading, setUploading] = useState<string | null>(null);
  const [sheetFor, setSheetFor] = useState<string | null>(null);
  const [uploadErrors, setUploadErrors] = useState<Record<string, string>>({});
  const [actionError, setActionError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [payBusy, setPayBusy] = useState(false);
  const [reviewBusy, setReviewBusy] = useState<string | null>(null);
  const [scheduleOpen, setScheduleOpen] = useState<"schedule" | "reschedule" | null>(null);
  const [noteFor, setNoteFor] = useState<"DOCUMENTS_DEFICIENT" | "REJECTED" | "APPROVED" | null>(null);

  const app = override && state.data && override.id === state.data.id ? override : state.data;

  if (!app) {
    if (state.status === "error") {
      return <ErrorState message="This application wasn't found, or you can't access it." onRetry={state.retry} />;
    }
    return <Loading />;
  }

  const isOwner = user?.role === "BUSINESS";
  const isOfficer = user?.role === "LM_OFFICER";
  const isInspector = isOfficer || user?.role === "GATC"; // same inspection machinery; only officers schedule/review
  const editable = isOwner && app.status === "DRAFT";
  const canSubmit = app.allowed_actions.includes("SUBMITTED");
  // APPROVED -> CERTIFICATE_ISSUED is system-only in the backend (never an allowed_actions edge), so
  // this is the one documented exception to "buttons come only from allowed_actions" (see CLAUDE.md).
  const canIssueCertificate = app.status === "APPROVED" && isOfficer;
  // The server doesn't guarantee row order after updates; keep the template order from /meta so
  // rows never jump around while the officer ticks them off.
  const templateOrder = meta.data?.document_review_checklist.map((i) => i.key) ?? [];
  const reviewItems = [...app.review_checklist].sort(
    (a, b) => templateOrder.indexOf(a.item_key) - templateOrder.indexOf(b.item_key),
  );
  // The backend is the authority (409 until every review item is checked); this just explains why.
  const reviewChecklistComplete = app.review_checklist.every((i) => i.checked);
  const requirementsMet = app.requirements.every((r) => !r.required || r.satisfied);
  const limits = meta.data?.limits;
  const atLimit = limits ? app.documents.length >= limits.max_documents : false;
  const deficiencyNote =
    app.status === "DOCUMENTS_DEFICIENT"
      ? ([...app.history].reverse().find((h) => h.to_status === "DOCUMENTS_DEFICIENT")?.note ?? null)
      : null;
  const docsOfType = (type: string) => app.documents.filter((d) => d.document_type === type);
  const shownTypes = editable
    ? app.requirements
    : app.requirements.filter((r) => r.required || docsOfType(r.document_type).length > 0);

  async function reload() {
    const fresh = await api<ApplicationDetail>(`/applications/${app!.id}`);
    setOverride(fresh);
  }

  async function addFile(documentType: string, pick: () => Promise<PickedFile | null>) {
    setUploadErrors((prev) => ({ ...prev, [documentType]: "" }));
    setUploading(documentType);
    try {
      const file = await pick();
      if (!file) return;
      await uploadDocument(app!.id, documentType, file);
      await reload();
    } catch (err) {
      setUploadErrors((prev) => ({
        ...prev,
        [documentType]: err instanceof ApiError ? err.message : err instanceof Error ? err.message : describeError(err),
      }));
    } finally {
      setUploading(null);
    }
  }

  async function viewDocument(doc: DocumentOut) {
    setActionError(null);
    try {
      // Short-lived signed URL: fetched on tap, opened, never stored.
      const { url } = await api<{ url: string; expires_in: number }>(`/documents/${doc.id}/url?disposition=inline`);
      await Linking.openURL(url);
    } catch (err) {
      setActionError(describeError(err));
    }
  }

  function confirmRemove(doc: DocumentOut) {
    Alert.alert("Remove this document?", doc.original_filename, [
      { text: "Cancel", style: "cancel" },
      {
        text: "Remove",
        style: "destructive",
        onPress: () => {
          void (async () => {
            setActionError(null);
            try {
              await api<void>(`/documents/${doc.id}`, { method: "DELETE" });
              await reload();
            } catch (err) {
              setActionError(describeError(err));
            }
          })();
        },
      },
    ]);
  }

  // Spec 12: purely informational; payment never gates any other step.
  async function mockPay() {
    setPayBusy(true);
    setActionError(null);
    try {
      setOverride(await api<ApplicationDetail>(`/applications/${app!.id}/mock-pay`, { method: "POST" }));
    } catch (err) {
      setActionError(describeError(err));
    } finally {
      setPayBusy(false);
    }
  }

  async function changeStatus(status: string, extra: Record<string, unknown> = {}) {
    setBusy(true);
    setActionError(null);
    try {
      const updated = await api<ApplicationDetail>(`/applications/${app!.id}/status`, {
        method: "PATCH",
        body: JSON.stringify({ status, ...extra }),
      });
      setOverride(updated);
      setNoteFor(null);
      setScheduleOpen(null);
    } catch (err) {
      setActionError(describeError(err));
    } finally {
      setBusy(false);
    }
  }

  async function startInspection() {
    setBusy(true);
    setActionError(null);
    try {
      const updated = await api<ApplicationDetail>(`/applications/${app!.id}/status`, {
        method: "PATCH",
        body: JSON.stringify({ status: "INSPECTION" }),
      });
      setOverride(updated);
      if (updated.inspection) router.push({ pathname: "/inspection/[id]", params: { id: updated.inspection.id } });
    } catch (err) {
      setActionError(describeError(err));
    } finally {
      setBusy(false);
    }
  }

  async function issueCertificate() {
    setBusy(true);
    setActionError(null);
    try {
      setOverride(await api<ApplicationDetail>(`/applications/${app!.id}/certificate`, { method: "POST" }));
    } catch (err) {
      setActionError(describeError(err));
    } finally {
      setBusy(false);
    }
  }

  async function reschedule(scheduledDate: string) {
    setBusy(true);
    setActionError(null);
    try {
      setOverride(
        await api<ApplicationDetail>(`/applications/${app!.id}/inspection`, {
          method: "PATCH",
          body: JSON.stringify({ scheduled_date: scheduledDate }),
        }),
      );
      setScheduleOpen(null);
    } catch (err) {
      setActionError(describeError(err));
    } finally {
      setBusy(false);
    }
  }

  // One request per toggle keeps each row's pending/error state simple (matches the web page).
  async function toggleReviewItem(itemKey: string, checked: boolean) {
    setReviewBusy(itemKey);
    setActionError(null);
    try {
      setOverride(
        await api<ApplicationDetail>(`/applications/${app!.id}/review-checklist`, {
          method: "PATCH",
          body: JSON.stringify({ items: [{ item_key: itemKey, checked }] }),
        }),
      );
    } catch (err) {
      setActionError(describeError(err));
    } finally {
      setReviewBusy(null);
    }
  }

  function confirmSubmit() {
    const resubmit = app!.status === "DOCUMENTS_DEFICIENT";
    Alert.alert(
      resubmit ? "Resubmit this application?" : "Submit this application?",
      "Your documents can't be changed after you submit.",
      [
        { text: "Cancel", style: "cancel" },
        { text: resubmit ? "Resubmit" : "Submit", onPress: () => void changeStatus("SUBMITTED") },
      ],
    );
  }

  const inst = app.instrument;
  return (
    <Screen hasHeader>
      <Muted>{app.application_number}</Muted>
      <View style={styles.titleRow}>
        <Title>{labelFor(meta.data?.application_types, app.application_type)}</Title>
        <StatusBadge status={app.status} label={labelFor(meta.data?.statuses, app.status)} />
      </View>
      <Muted>
        {inst.instrument_uid} · {inst.manufacturer} {inst.model} · S/N {inst.serial_number} · {inst.capacity}{" "}
        {inst.capacity_unit}
      </Muted>
      {app.verification_mode ? (
        <Muted>Verification mode: {labelFor(meta.data?.verification_modes, app.verification_mode)}</Muted>
      ) : null}

      {actionError ? <ErrorText>{actionError}</ErrorText> : null}
      {deficiencyNote ? <InfoText>Documents deficient: {deficiencyNote}</InfoText> : null}

      {/* Buttons come from allowed_actions: the app never guesses permissions. */}
      {canSubmit ? (
        <View style={{ gap: 6 }}>
          <Button
            label={app.status === "DOCUMENTS_DEFICIENT" ? "Resubmit application" : "Submit application"}
            onPress={confirmSubmit}
            disabled={!requirementsMet}
            loading={busy}
          />
          {!requirementsMet ? <Muted>Upload every required document to submit.</Muted> : null}
        </View>
      ) : null}

      {isInspector && (app.allowed_actions.length > 0 || app.inspection || app.can_reschedule || canIssueCertificate) ? (
        <View style={{ gap: 8 }}>
          {isOfficer && app.allowed_actions.includes("SCHEDULED") ? (
            <View style={{ gap: 6 }}>
              <Button
                label="Schedule inspection"
                onPress={() => {
                  setActionError(null);
                  setScheduleOpen("schedule");
                }}
                disabled={!reviewChecklistComplete || busy}
              />
              {!reviewChecklistComplete ? <Muted>Check off every document review item before scheduling.</Muted> : null}
            </View>
          ) : null}
          {isOfficer && app.can_reschedule ? (
            <Button
              label="Change inspection date"
              variant="secondary"
              onPress={() => {
                setActionError(null);
                setScheduleOpen("reschedule");
              }}
              disabled={busy}
            />
          ) : null}
          {app.allowed_actions.includes("INSPECTION") ? (
            <Button label="Start inspection" onPress={() => void startInspection()} loading={busy} />
          ) : null}
          {app.inspection && app.status !== "SCHEDULED" ? (
            <Button
              label={app.status === "INSPECTION" && !app.inspection.submitted_at ? "Continue inspection" : "View inspection"}
              variant={app.status === "INSPECTION" && !app.inspection.submitted_at ? "primary" : "secondary"}
              onPress={() => router.push({ pathname: "/inspection/[id]", params: { id: app.inspection!.id } })}
            />
          ) : null}
          {app.allowed_actions.includes("DOCUMENT_REVIEW") ? (
            <Button label="Start review" onPress={() => void changeStatus("DOCUMENT_REVIEW")} loading={busy} />
          ) : null}
          {app.allowed_actions.includes("DOCUMENTS_DEFICIENT") ? (
            <Button label="Send back (documents deficient)" variant="secondary" onPress={() => setNoteFor("DOCUMENTS_DEFICIENT")} disabled={busy} />
          ) : null}
          {app.allowed_actions.includes("APPROVED") ? (
            <Button label="Approve" onPress={() => setNoteFor("APPROVED")} disabled={busy} />
          ) : null}
          {app.allowed_actions.includes("REJECTED") ? (
            <Button label="Reject" variant="secondary" onPress={() => setNoteFor("REJECTED")} disabled={busy} />
          ) : null}
          {canIssueCertificate ? <Button label="Issue certificate" onPress={() => void issueCertificate()} loading={busy} /> : null}
        </View>
      ) : null}

      <View style={styles.card}>
        <Text style={styles.sectionTitle}>Documents</Text>
        {shownTypes.length === 0 ? <Muted>No documents.</Muted> : null}
        {shownTypes.map((r) => (
          <View key={r.document_type} style={styles.slot}>
            <Text style={styles.slotTitle}>
              {r.satisfied ? "✓ " : ""}
              {r.label}
              {r.required ? "" : " (optional)"}
            </Text>
            {docsOfType(r.document_type).map((d) => (
              <View key={d.id} style={styles.docRow}>
                <View style={{ flex: 1 }}>
                  <Text style={{ color: colors.text }} numberOfLines={1}>
                    {d.original_filename}
                  </Text>
                  <Muted>{formatBytes(d.size_bytes)}</Muted>
                </View>
                <Text style={styles.link} onPress={() => void viewDocument(d)}>
                  View
                </Text>
                {editable ? (
                  <Text style={[styles.link, { color: colors.danger }]} onPress={() => confirmRemove(d)}>
                    Remove
                  </Text>
                ) : null}
              </View>
            ))}
            {editable && !atLimit ? (
              <Button
                label={uploading === r.document_type ? "Uploading…" : "Add file"}
                variant="secondary"
                onPress={() => setSheetFor(r.document_type)}
                loading={uploading === r.document_type}
                disabled={uploading !== null}
              />
            ) : null}
            {uploadErrors[r.document_type] ? <ErrorText>{uploadErrors[r.document_type]}</ErrorText> : null}
          </View>
        ))}
        {editable && atLimit ? <Muted>Document limit reached ({limits?.max_documents}).</Muted> : null}
      </View>

      {reviewItems.length > 0 ? (
        <View style={styles.card}>
          <Text style={styles.sectionTitle}>Document review checklist</Text>
          {reviewItems.map((item) =>
            app.status === "DOCUMENT_REVIEW" && isOfficer ? (
              <Text
                key={item.item_key}
                accessibilityRole="checkbox"
                style={[styles.checkRow, reviewBusy !== null && { opacity: 0.6 }]}
                onPress={() => reviewBusy === null && void toggleReviewItem(item.item_key, !item.checked)}
              >
                {item.checked ? "☑" : "☐"} {item.label}
              </Text>
            ) : (
              <Muted key={item.item_key}>
                {item.checked ? "✓" : "•"} {item.label}
              </Muted>
            ),
          )}
        </View>
      ) : null}

      {app.inspection ? (
        <View style={styles.card}>
          <Text style={styles.sectionTitle}>Inspection</Text>
          <Muted>
            Scheduled {app.inspection.scheduled_date} · {app.inspection.assigned_officer_name}
          </Muted>
        </View>
      ) : null}

      {app.certificate ? (
        <View style={styles.card}>
          <Text style={styles.sectionTitle}>Certificate</Text>
          <Muted>
            {app.certificate.certificate_number} · valid until {app.certificate.valid_until}
          </Muted>
          <Button
            label="View certificate"
            variant="secondary"
            onPress={() => openInTab({ pathname: "/certificates/[id]", params: { id: app.certificate!.id } })}
          />
        </View>
      ) : null}

      <View style={styles.card}>
        <Text style={styles.sectionTitle}>Payment</Text>
        <Muted>{labelFor(meta.data?.payment_statuses, app.payment?.status ?? "NOT_PAID")}</Muted>
        <Muted>Informational only (prototype): payment status doesn&apos;t affect any other step.</Muted>
        {isOwner && (!app.payment || app.payment.status !== "PAID") ? (
          <Button label="Mock pay (prototype)" variant="secondary" onPress={() => void mockPay()} loading={payBusy} />
        ) : null}
      </View>

      <View style={styles.card}>
        <Text style={styles.sectionTitle}>Status history</Text>
        {app.history.map((h, idx) => (
          <View key={`${h.created_at}-${idx}`} style={{ gap: 2 }}>
            <Text style={{ color: colors.text, fontWeight: "600" }}>
              {labelFor(meta.data?.statuses, h.to_status)}
            </Text>
            <Muted>
              {h.actor_name} · {formatDateTime(h.created_at)}
            </Muted>
            {h.note ? <Muted>“{h.note}”</Muted> : null}
          </View>
        ))}
      </View>

      {scheduleOpen && meta.data ? (
        <ScheduleDialog
          key={scheduleOpen}
          visible
          app={app}
          timezone={meta.data.scheduling.timezone}
          maxDaysAhead={meta.data.scheduling.max_days_ahead}
          reschedule={scheduleOpen === "reschedule"}
          busy={busy}
          error={actionError}
          onConfirm={(body) => (scheduleOpen === "reschedule" ? void reschedule(body.scheduled_date) : void changeStatus("SCHEDULED", body))}
          onClose={() => setScheduleOpen(null)}
        />
      ) : null}

      <NoteDialog
        key={noteFor ?? "closed"}
        visible={noteFor !== null}
        title={
          noteFor === "REJECTED"
            ? "Reject this application?"
            : noteFor === "APPROVED"
              ? "Approve this application?"
              : "Send back as documents deficient?"
        }
        description={
          noteFor === "REJECTED"
            ? "The business will see your reason and must re-apply."
            : noteFor === "APPROVED"
              ? "The instrument stays location-locked until the certificate is issued."
              : "This doesn't reject the application: the business can fix the issue and resubmit."
        }
        label={noteFor === "REJECTED" ? "Reason" : noteFor === "APPROVED" ? "Note (optional)" : "What's missing or wrong"}
        minLength={noteFor === "APPROVED" ? 0 : NOTE_MIN}
        confirmLabel={noteFor === "REJECTED" ? "Reject" : noteFor === "APPROVED" ? "Approve" : "Send back"}
        destructive={noteFor === "REJECTED"}
        busy={busy}
        onConfirm={(note) => void changeStatus(noteFor!, note ? { note } : {})}
        onClose={() => setNoteFor(null)}
      />

      <ChoiceModal
        visible={sheetFor !== null}
        title="Add a file"
        onClose={() => setSheetFor(null)}
        options={[
          { label: "Take a photo", onPress: () => void addFile(sheetFor!, () => pickPhoto("camera")) },
          { label: "Choose a photo", onPress: () => void addFile(sheetFor!, () => pickPhoto("library")) },
          {
            label: "Choose a PDF",
            onPress: () => void addFile(sheetFor!, () => pickPdf(limits?.max_file_bytes ?? 10 * 1024 * 1024)),
          },
        ]}
      />
    </Screen>
  );
}

const styles = StyleSheet.create({
  titleRow: { gap: 6 },
  card: { backgroundColor: colors.card, borderRadius: 12, padding: 14, gap: 12, borderWidth: 1, borderColor: colors.border },
  sectionTitle: { fontSize: 16, fontWeight: "700", color: colors.text },
  slot: { gap: 8, paddingTop: 4 },
  slotTitle: { fontSize: 14, fontWeight: "600", color: colors.text },
  docRow: { flexDirection: "row", alignItems: "center", gap: 14 },
  checkRow: { fontSize: 15, color: colors.text, paddingVertical: 8 },
  link: { color: colors.primary, fontWeight: "600", paddingVertical: 6 },
});
