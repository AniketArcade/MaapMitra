import type { Application } from "@api-types";
import { router, useFocusEffect } from "expo-router";
import { useCallback, useEffect, useRef, useState } from "react";
import { FlatList, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";

import { StatusBadge } from "@/components/status-badge";
import { Button, Empty, ErrorState, Loading, Muted, Screen } from "@/components/ui";
import { getApplicationMeta, labelFor } from "@/lib/meta";
import { colors } from "@/lib/theme";
import { useAsync } from "@/lib/use-async";
import { usePagedList } from "@/lib/use-paged-list";

export default function ApplicationsList() {
  const [text, setText] = useState("");
  const meta = useAsync(getApplicationMeta);
  const { list, filters, error, loading, loadMore, restart, setFilter } =
    usePagedList<Application>("/applications");
  const status = filters.status ?? "";
  const query = filters.q ?? "";

  useEffect(() => {
    const t = setTimeout(() => setFilter({ q: text.trim() }), 300);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- setFilter identity changes every render
  }, [text]);

  // Coming back from create/detail: reload from page 1.
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
      <Button label="New application" onPress={() => router.push("/applications/new")} />
      <TextInput
        value={text}
        onChangeText={setText}
        placeholder="Search by application number or instrument"
        placeholderTextColor={colors.muted}
        maxLength={100}
        autoCapitalize="none"
        autoCorrect={false}
        style={styles.search}
      />
      {/* Status filter values come from /applications/meta, in lifecycle order. */}
      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 8 }}>
        {[{ value: "", label: "All" }, ...(meta.data?.statuses ?? [])].map((s) => (
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
          {list.total} application{list.total === 1 ? "" : "s"}
        </Muted>
      ) : null}
    </View>
  );

  if (!list && loading) return <Loading label="Loading applications…" />;
  if (!list && error) return <ErrorState message={error} onRetry={restart} />;

  return (
    <Screen scroll={false} hasHeader>
      <FlatList
        data={list?.items ?? []}
        refreshing={false}
        onRefresh={restart}
        keyExtractor={(a) => a.id}
        ListHeaderComponent={header}
        ListEmptyComponent={
          <Empty
            message={
              query || status
                ? "No applications match your filters."
                : "No applications yet. Open an instrument to apply for verification."
            }
          />
        }
        ListFooterComponent={
          <View style={{ paddingVertical: 12, gap: 8 }}>
            {error ? <Muted>{error}</Muted> : null}
            {list && list.items.length < list.total ? (
              <Button label="Load more" variant="secondary" onPress={loadMore} loading={loading} />
            ) : null}
          </View>
        }
        ItemSeparatorComponent={() => <View style={{ height: 10 }} />}
        renderItem={({ item: a }) => (
          <Pressable
            onPress={() => router.push({ pathname: "/applications/[id]", params: { id: a.id } })}
            style={styles.card}
          >
            <View style={styles.cardTop}>
              <Text style={styles.number}>{a.application_number}</Text>
              <StatusBadge status={a.status} label={labelFor(meta.data?.statuses, a.status)} />
            </View>
            <Text style={styles.cardTitle}>
              {a.instrument.manufacturer} {a.instrument.model} · {a.instrument.capacity} {a.instrument.capacity_unit}
            </Text>
            <Text style={styles.muted}>
              {a.instrument.instrument_uid} · S/N {a.instrument.serial_number}
            </Text>
          </Pressable>
        )}
      />
    </Screen>
  );
}

const styles = StyleSheet.create({
  search: {
    minHeight: 48,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 10,
    paddingHorizontal: 12,
    backgroundColor: colors.card,
    color: colors.text,
    fontSize: 16,
  },
  chip: { borderRadius: 999, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, paddingHorizontal: 12, paddingVertical: 8 },
  chipActive: { backgroundColor: colors.primary, borderColor: colors.primary },
  chipText: { color: colors.text, fontSize: 13, fontWeight: "600" },
  chipTextActive: { color: colors.primaryText },
  card: { backgroundColor: colors.card, borderRadius: 12, padding: 14, gap: 4, borderWidth: 1, borderColor: colors.border },
  cardTop: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", gap: 8 },
  number: { fontSize: 13, color: colors.muted, fontFamily: "monospace", flexShrink: 1 },
  cardTitle: { fontSize: 16, fontWeight: "600", color: colors.text },
  muted: { fontSize: 14, color: colors.muted },
});
