import { StyleSheet, Text, View } from "react-native";

// Colors only: the label always comes from /applications/meta (never hard-coded statuses).
const TONES: Record<string, { bg: string; fg: string }> = {
  DRAFT: { bg: "#e5e7eb", fg: "#374151" },
  SUBMITTED: { bg: "#dbeafe", fg: "#1e40af" },
  DOCUMENT_REVIEW: { bg: "#dbeafe", fg: "#1e40af" },
  DOCUMENTS_DEFICIENT: { bg: "#fef3c7", fg: "#92400e" },
  SCHEDULED: { bg: "#ede9fe", fg: "#5b21b6" },
  INSPECTION: { bg: "#ede9fe", fg: "#5b21b6" },
  APPROVED: { bg: "#dcfce7", fg: "#166534" },
  CERTIFICATE_ISSUED: { bg: "#dcfce7", fg: "#166534" },
  REJECTED: { bg: "#fee2e2", fg: "#991b1b" },
};

export function StatusBadge({ status, label }: { status: string; label: string }) {
  const tone = TONES[status] ?? { bg: "#e5e7eb", fg: "#374151" };
  return (
    <View style={[styles.badge, { backgroundColor: tone.bg }]}>
      <Text style={[styles.text, { color: tone.fg }]}>{label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  badge: { borderRadius: 999, paddingHorizontal: 10, paddingVertical: 4, alignSelf: "flex-start" },
  text: { fontSize: 12, fontWeight: "700" },
});
