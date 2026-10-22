import type { ReactNode } from "react";
import { ActivityIndicator, StyleSheet, Text, View } from "react-native";

import { Button, ErrorText } from "@/components/ui";
import { colors } from "@/lib/theme";
import type { Async } from "@/lib/use-async";

/** A dashboard card with independent loading / error / retry, so one failure never blanks the screen. */
export function Section<T>({
  title,
  state,
  errorMessage,
  children,
}: {
  title: string;
  state: Async<T>;
  errorMessage: string;
  children: (data: T) => ReactNode;
}) {
  return (
    <View style={styles.card}>
      <Text style={styles.title}>{title}</Text>
      {state.data !== null ? (
        children(state.data)
      ) : state.status === "error" ? (
        <View style={{ gap: 8 }}>
          <ErrorText>{errorMessage}</ErrorText>
          <Button label="Try again" variant="secondary" onPress={state.retry} />
        </View>
      ) : (
        <ActivityIndicator color={colors.primary} />
      )}
    </View>
  );
}

export function Chip({ children }: { children: ReactNode }) {
  return (
    <View style={styles.chip}>
      <Text style={styles.chipText}>{children}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  card: { backgroundColor: colors.card, borderRadius: 12, padding: 14, gap: 10, borderWidth: 1, borderColor: colors.border },
  title: { fontSize: 16, fontWeight: "700", color: colors.text },
  chip: { backgroundColor: "#eef2ff", borderRadius: 999, paddingHorizontal: 10, paddingVertical: 6 },
  chipText: { color: colors.primary, fontSize: 13, fontWeight: "600" },
});
