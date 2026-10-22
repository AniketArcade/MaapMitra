import type { ApplicationDetail, DocumentOut } from "@api-types";
import { useLocalSearchParams } from "expo-router";
import { useState } from "react";
import { Alert, Linking, StyleSheet, Text, View } from "react-native";

import { StatusBadge } from "@/components/status-badge";
import { Button, ChoiceModal, ErrorState, ErrorText, InfoText, Loading, Muted, Screen, Title } from "@/components/ui";
import { ApiError, api, describeError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { getApplicationMeta, labelFor } from "@/lib/meta";
import { colors } from "@/lib/theme";
import { pickPdf, pickPhoto, uploadDocument, type PickedFile } from "@/lib/upload";
import { useAsync } from "@/lib/use-async";

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(0)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

function formatDateTime(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleString(undefined, { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });
}

export default function ApplicationDetailScreen() {
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

  const app = override && state.data && override.id === state.data.id ? override : state.data;

  if (!app) {
    if (state.status === "error") {
      return <ErrorState message="This application wasn't found, or you can't access it." onRetry={state.retry} />;
    }
    return <Loading />;
  }

  const isOwner = user?.role === "BUSINESS";
  const editable = isOwner && app.status === "DRAFT";
  const canSubmit = app.allowed_actions.includes("SUBMITTED");
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

  async function submitApplication() {
    setBusy(true);
    setActionError(null);
    try {
      const updated = await api<ApplicationDetail>(`/applications/${app!.id}/status`, {
        method: "PATCH",
        body: JSON.stringify({ status: "SUBMITTED" }),
      });
      setOverride(updated);
    } catch (err) {
      setActionError(describeError(err));
    } finally {
      setBusy(false);
    }
  }

  function confirmSubmit() {
    const resubmit = app!.status === "DOCUMENTS_DEFICIENT";
    Alert.alert(
      resubmit ? "Resubmit this application?" : "Submit this application?",
      "Your documents can't be changed after you submit.",
      [
        { text: "Cancel", style: "cancel" },
        { text: resubmit ? "Resubmit" : "Submit", onPress: () => void submitApplication() },
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
        </View>
      ) : null}

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
  link: { color: colors.primary, fontWeight: "600", paddingVertical: 6 },
});
