import type { Certificate } from "@api-types";
import { router, useFocusEffect } from "expo-router";
import { useCallback, useRef } from "react";
import { FlatList, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";

import { Button, Empty, ErrorState, Loading, Muted, Screen } from "@/components/ui";
import { colors } from "@/lib/theme";
import { usePagedList } from "@/lib/use-paged-list";
import { formatDate } from "@/lib/verify";

// ASSUMPTION: certificate statuses have no /meta endpoint (the web filter hard-codes them too);
// they mirror the backend's CertificateStatus enum.
const STATUSES = ["VALID", "EXPIRED", "REVOKED", "SUPERSEDED"];

const TONE: Record<string, { bg: string; fg: string }> = {
  VALID: { bg: "#dcfce7", fg: "#166534" },
  EXPIRED: { bg: "#fef3c7", fg: "#92400e" },
  REVOKED: { bg: "#fee2e2", fg: "#991b1b" },
  SUPERSEDED: { bg: "#fef3c7", fg: "#92400e" },
};

/** Certificates visible to the caller (scoped by the backend), with a status filter and paging. */
export function CertificateList() {
  const { list, filters, error, loading, loadMore, restart, setFilter } = usePagedList<Certificate>("/certificates");
  const status = filters.status ?? "";

  const first = useRef(true);
  useFocusEffect(
    useCallback(() => {
      if (first.current) first.current = false;
      else restart();
      // eslint-disable-next-line react-hooks/exhaustive-deps -- restart identity changes every render
    }, []),
  );

  const header = (
    <View style={{ gap: 12, marginBottom: 12 }}>
      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 8 }}>
        {[{ value: "", label: "All" }, ...STATUSES.map((s) => ({ value: s, label: s[0] + s.slice(1).toLowerCase() }))].map((s) => (
          <Pressable
            key={s.value || "all"}
            onPress={() => setFilter({ status: s.value })}
            style={[styles.chip, status === s.value && styles.chipActive]}
          >
            <Text style={[styles.chipText, status === s.value && styles.chipTextActive]}>{s.label}</Text>
          </Pressable>
        ))}
      </ScrollView>
      {list ? (
        <Muted>
          {list.total} certificate{list.total === 1 ? "" : "s"}
        </Muted>
      ) : null}
    </View>
  );

  if (!list && loading) return <Loading label="Loading certificates…" />;
  if (!list && error) return <ErrorState message={error} onRetry={restart} />;

  return (
    <Screen scroll={false} hasHeader>
      <FlatList
        data={list?.items ?? []}
        keyExtractor={(c) => c.id}
        refreshing={false}
        onRefresh={restart}
        ListHeaderComponent={header}
        ListEmptyComponent={<Empty message={status ? "No certificates with this status." : "No certificates yet."} />}
        ListFooterComponent={
          <View style={{ paddingVertical: 12, gap: 8 }}>
            {error ? <Muted>{error}</Muted> : null}
            {list && list.items.length < list.total ? (
              <Button label="Load more" variant="secondary" onPress={loadMore} loading={loading} />
            ) : null}
          </View>
        }
        ItemSeparatorComponent={() => <View style={{ height: 10 }} />}
        renderItem={({ item: c }) => {
          const tone = TONE[c.status] ?? { bg: "#e5e7eb", fg: "#374151" };
          return (
            <Pressable onPress={() => router.push({ pathname: "/certificates/[id]", params: { id: c.id } })} style={styles.card}>
              <View style={styles.cardTop}>
                <Text style={styles.number}>{c.certificate_number}</Text>
                <View style={[styles.badge, { backgroundColor: tone.bg }]}>
                  <Text style={[styles.badgeText, { color: tone.fg }]}>{c.status}</Text>
                </View>
              </View>
              <Text style={styles.cardTitle}>
                {c.manufacturer} {c.model} · {c.capacity} {c.capacity_unit}
              </Text>
              <Text style={styles.muted}>
                S/N {c.serial_number} · valid until {formatDate(c.valid_until)}
                {c.is_expiring_soon ? " · expiring soon" : ""}
              </Text>
            </Pressable>
          );
        }}
      />
    </Screen>
  );
}

const styles = StyleSheet.create({
  chip: { borderRadius: 999, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, paddingHorizontal: 12, paddingVertical: 8 },
  chipActive: { backgroundColor: colors.primary, borderColor: colors.primary },
  chipText: { color: colors.text, fontSize: 13, fontWeight: "600" },
  chipTextActive: { color: colors.primaryText },
  card: { backgroundColor: colors.card, borderRadius: 12, padding: 14, gap: 4, borderWidth: 1, borderColor: colors.border },
  cardTop: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", gap: 8 },
  number: { fontSize: 13, color: colors.muted, fontFamily: "monospace", flexShrink: 1 },
  badge: { borderRadius: 999, paddingHorizontal: 10, paddingVertical: 4 },
  badgeText: { fontSize: 12, fontWeight: "700" },
  cardTitle: { fontSize: 16, fontWeight: "600", color: colors.text },
  muted: { fontSize: 14, color: colors.muted },
});
