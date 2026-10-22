import type { VerifyResult } from "@api-types";
import { StyleSheet, Text, View } from "react-native";

import { formatDate } from "@/lib/verify";

const BADGE: Record<string, { label: string; color: string; bg: string }> = {
  VALID: { label: "✓ VALID", color: "#166534", bg: "#dcfce7" },
  EXPIRED: { label: "⚠ EXPIRED", color: "#92400e", bg: "#fef3c7" },
  REVOKED: { label: "✕ REVOKED", color: "#991b1b", bg: "#fee2e2" },
  SUPERSEDED: { label: "⚠ SUPERSEDED", color: "#92400e", bg: "#fef3c7" },
};

export function VerifyResultCard({ result }: { result: VerifyResult }) {
  const badge = BADGE[result.status] ?? { label: result.status, color: "#374151", bg: "#e5e7eb" };
  const rows: [string, string][] = [
    ["Instrument", result.instrument_type_label],
    ["Instrument ID", result.instrument_uid],
    ["Manufacturer", result.manufacturer],
    ["Model", result.model],
    ["Serial number", result.serial_number],
    ["Valid", `${formatDate(result.valid_from)} – ${formatDate(result.valid_until)}`],
    ["Issued by", result.issued_by],
  ];
  return (
    <View style={styles.card}>
      <Text style={styles.number}>{result.certificate_number}</Text>
      <View style={[styles.badge, { backgroundColor: badge.bg }]}>
        <Text style={[styles.badgeText, { color: badge.color }]}>{badge.label}</Text>
      </View>
      {rows.map(([label, value]) => (
        <View key={label} style={styles.row}>
          <Text style={styles.label}>{label}</Text>
          <Text style={styles.value}>{value}</Text>
        </View>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  card: { backgroundColor: "#fff", borderRadius: 12, padding: 16, gap: 12, borderWidth: 1, borderColor: "#e5e7eb" },
  number: { fontSize: 12, color: "#6b7280", fontFamily: "monospace" },
  badge: { borderRadius: 10, paddingVertical: 14, alignItems: "center" },
  badgeText: { fontSize: 22, fontWeight: "700" },
  row: { flexDirection: "row", justifyContent: "space-between", gap: 12 },
  label: { color: "#6b7280", fontSize: 14 },
  value: { color: "#111827", fontSize: 14, flexShrink: 1, textAlign: "right" },
});
