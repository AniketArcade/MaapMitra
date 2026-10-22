import type { Instrument } from "@api-types";
import { router, useLocalSearchParams } from "expo-router";
import { useState } from "react";
import { Alert, StyleSheet, Text, View } from "react-native";

import { Button, ErrorState, Loading, Muted, Screen, Title, ErrorText } from "@/components/ui";
import { ApiError, api, describeError } from "@/lib/api";
import { getInstrumentMeta, regionLabel, typeLabel } from "@/lib/meta";
import { colors } from "@/lib/theme";
import { useAsync } from "@/lib/use-async";

function Row({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.row}>
      <Text style={styles.label}>{label}</Text>
      <Text style={styles.value}>{value}</Text>
    </View>
  );
}

export default function InstrumentDetail() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const state = useAsync(() => api<Instrument>(`/instruments/${id}`));
  const meta = useAsync(getInstrumentMeta);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  if (!state.data) {
    if (state.status === "error") {
      // 404 covers both "missing" and "not yours"; the app can't tell them apart (by design).
      return <ErrorState message="This instrument wasn't found, or you can't access it." onRetry={state.retry} />;
    }
    return <Loading />;
  }

  const i = state.data;

  function confirmDelete() {
    Alert.alert(
      "Delete this instrument?",
      `${i.instrument_uid} (S/N ${i.serial_number}) will be permanently removed. This can't be undone.`,
      [
        { text: "Cancel", style: "cancel" },
        { text: "Delete", style: "destructive", onPress: () => void doDelete() },
      ],
    );
  }

  async function doDelete() {
    setDeleting(true);
    setDeleteError(null);
    try {
      await api<void>(`/instruments/${i.id}`, { method: "DELETE" });
      router.replace("/instruments");
    } catch (err) {
      setDeleteError(err instanceof ApiError ? err.message : describeError(err));
      setDeleting(false);
    }
  }

  return (
    <Screen hasHeader>
      <Muted>{i.instrument_uid}</Muted>
      <Title>
        {typeLabel(meta.data, i.instrument_type)} · {i.capacity} {i.capacity_unit}
      </Title>

      {deleteError ? <ErrorText>{deleteError}</ErrorText> : null}

      <View style={styles.card}>
        <Row label="Owner" value={i.organization_name} />
        <Row label="Manufacturer" value={i.manufacturer} />
        <Row label="Model" value={i.model} />
        <Row label="Serial number" value={i.serial_number} />
        <Row label="Maximum capacity" value={`${i.capacity} ${i.capacity_unit}`} />
        <Row label="Accuracy class" value={i.accuracy_class ? `Class ${i.accuracy_class}` : "Not specified"} />
        <Row label="Can be transported?" value={i.transportable ? "Yes (office/test centre)" : "No (on-site)"} />
        <Row label="Address" value={i.address} />
        <Row label="Region" value={regionLabel(meta.data, i.state_code, i.district_code)} />
        <Row
          label="Coordinates"
          value={i.latitude !== null && i.longitude !== null ? `${i.latitude}, ${i.longitude}` : "Not provided"}
        />
      </View>

      {i.active_application ? (
        <Muted>
          Application in progress: {i.active_application.application_number}. While it is in progress, the serial
          number, capacity and location can&apos;t be changed.
        </Muted>
      ) : null}

      <Button label="Edit" variant="secondary" onPress={() => router.push({ pathname: "/instruments/[id]/edit", params: { id: i.id } })} />
      <Button label="Delete" variant="secondary" onPress={confirmDelete} loading={deleting} />
    </Screen>
  );
}

const styles = StyleSheet.create({
  card: { backgroundColor: colors.card, borderRadius: 12, padding: 14, gap: 10, borderWidth: 1, borderColor: colors.border },
  row: { flexDirection: "row", justifyContent: "space-between", gap: 12 },
  label: { color: colors.muted, fontSize: 14 },
  value: { color: colors.text, fontSize: 14, flexShrink: 1, textAlign: "right" },
});
