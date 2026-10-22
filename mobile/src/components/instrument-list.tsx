import type { Instrument } from "@api-types";
import { useFocusEffect, router } from "expo-router";
import { useCallback, useEffect, useRef, useState } from "react";
import { FlatList, Pressable, StyleSheet, Text, TextInput, View } from "react-native";

import { Button, Empty, ErrorState, Loading, Muted, Screen } from "@/components/ui";
import { getInstrumentMeta, typeLabel } from "@/lib/meta";
import { colors } from "@/lib/theme";
import { useAsync } from "@/lib/use-async";
import { usePagedList } from "@/lib/use-paged-list";

export function InstrumentList({
  canCreate = false,
  onOpen,
}: {
  canCreate?: boolean;
  onOpen: (id: string) => void;
}) {
  const [text, setText] = useState("");
  const meta = useAsync(getInstrumentMeta); // labels only; codes are the fallback
  const { list, filters, error, loading, loadMore, restart, setFilter } = usePagedList<Instrument>("/instruments");
  const query = filters.q ?? "";

  useEffect(() => {
    const t = setTimeout(() => setFilter({ q: text.trim() }), 300);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- setFilter identity changes every render
  }, [text]);

  // Coming back from create/edit/delete: reload from page 1.
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
      {canCreate ? <Button label="Register instrument" onPress={() => router.push("/instruments/new")} /> : null}
      <TextInput
        value={text}
        onChangeText={setText}
        placeholder="Search by serial, UID, manufacturer or model"
        placeholderTextColor={colors.muted}
        maxLength={100}
        autoCapitalize="none"
        autoCorrect={false}
        style={styles.search}
      />
      {list ? (
        <Muted>
          {list.total} instrument{list.total === 1 ? "" : "s"}
        </Muted>
      ) : null}
    </View>
  );

  if (!list && loading) return <Loading label="Loading instruments…" />;
  if (!list && error) return <ErrorState message={error} onRetry={restart} />;

  return (
    <Screen scroll={false} hasHeader>
      <FlatList
        data={list?.items ?? []}
        refreshing={false}
        onRefresh={restart}
        keyExtractor={(i) => i.id}
        ListHeaderComponent={header}
        ListEmptyComponent={
          <Empty message={query ? "No instruments match your search." : canCreate ? "No instruments yet. Register your first one." : "No instruments to show."} />
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
        renderItem={({ item: i }) => (
          <Pressable
            onPress={() => onOpen(i.id)}
            style={styles.card}
          >
            <Text style={styles.uid}>{i.instrument_uid}</Text>
            <Text style={styles.cardTitle}>
              {typeLabel(meta.data, i.instrument_type)} · {i.capacity} {i.capacity_unit}
            </Text>
            <Text style={styles.muted}>
              {i.manufacturer} {i.model} · S/N {i.serial_number}
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
  card: { backgroundColor: colors.card, borderRadius: 12, padding: 14, gap: 2, borderWidth: 1, borderColor: colors.border },
  uid: { fontSize: 12, color: colors.muted, fontFamily: "monospace" },
  cardTitle: { fontSize: 16, fontWeight: "600", color: colors.text },
  muted: { fontSize: 14, color: colors.muted },
});
