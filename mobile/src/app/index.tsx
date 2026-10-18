import type { Role } from "@api-types";
import { StyleSheet, Text, View } from "react-native";

// Placeholder: proves the shared API types resolve. Replaced by the auth shell in Phase 4.
const AUDIENCES: Role[] = ["BUSINESS", "LM_OFFICER", "GATC"];

export default function Home() {
  return (
    <View style={styles.container}>
      <Text style={styles.title}>MaapMitra</Text>
      <Text style={styles.sub}>{AUDIENCES.join(" · ")}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, alignItems: "center", justifyContent: "center", gap: 8 },
  title: { fontSize: 32, fontWeight: "700" },
  sub: { fontSize: 14, color: "#666" },
});
