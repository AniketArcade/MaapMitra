import type { Instrument, Page } from "@api-types";
import { useFocusEffect, router } from "expo-router";
import { useCallback, useEffect, useRef, useState } from "react";
import { FlatList, Pressable, StyleSheet, Text, TextInput, View } from "react-native";

import { Button, Empty, ErrorState, Loading, Muted, Screen } from "@/components/ui";
import { api, describeError } from "@/lib/api";
import { getInstrumentMeta, typeLabel } from "@/lib/meta";
import { colors } from "@/lib/theme";
import { useAsync } from "@/lib/use-async";

const PAGE_SIZE = 20;

type List = { items: Instrument[]; total: number };

// Paged, server-side search: `total` comes from the API, never counted on the client.
function useInstrumentList() {
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(1);
  const [reload, setReload] = useState(0);
  const [list, setList] = useState<List | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    const params = new URLSearchParams({ page: String(page), page_size: String(PAGE_SIZE) });
    if (query) params.set("q", query);
    api<Page<Instrument>>(`/instruments?${params}`).then(
      (data) => {
        if (cancelled) return;
        setList((prev) => ({
          total: data.total,
          items: page === 1 || !prev ? data.items : [...prev.items, ...data.items],
        }));
        setError(null);
        setLoading(false);
      },
      (err: unknown) => {
        if (cancelled) return;
        setError(describeError(err));
        setLoading(false);
      },
    );
    return () => {
      cancelled = true;
    };
  }, [query, page, reload]);

  return {
    list,
    query,
    error,
    loading,
    /** A new search always starts from page 1. */
    search: (q: string) => {
      setQuery(q);
      setPage(1);
    },
    loadMore: () => {
      setLoading(true);
      setPage((p) => p + 1);
    },
    /** Starts again from page 1 (new search, or returning from a form). */
    restart: () => {
      setLoading(true);
      setPage(1);
      setReload((n) => n + 1);
    },
  };
}

export default function InstrumentsList() {
  const [text, setText] = useState("");
  const meta = useAsync(getInstrumentMeta); // labels only; codes are the fallback
  const { list, query, error, loading, loadMore, restart, search } = useInstrumentList();

  useEffect(() => {
    const t = setTimeout(() => search(text.trim()), 300);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- search identity changes every render
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
      <Button label="Register instrument" onPress={() => router.push("/instruments/new")} />
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
        keyExtractor={(i) => i.id}
        ListHeaderComponent={header}
        ListEmptyComponent={
          <Empty message={query ? "No instruments match your search." : "No instruments yet. Register your first one."} />
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
            onPress={() => router.push({ pathname: "/instruments/[id]", params: { id: i.id } })}
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
