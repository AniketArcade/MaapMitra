import type { AdminCertificateStats, Certificate } from "@api-types";
import { useFocusEffect } from "expo-router";
import { useCallback, useRef } from "react";
import { FlatList, Pressable, StyleSheet, Text, View } from "react-native";

import { Button, Empty, ErrorState, Loading, Muted, Screen } from "@/components/ui";
import { api } from "@/lib/api";
import { getApplicationMeta } from "@/lib/meta";
import { openInTab } from "@/lib/nav";
import { addDaysToIsoDate, todayInTimezone } from "@/lib/scheduling";
import { colors } from "@/lib/theme";
import { useAsync } from "@/lib/use-async";
import { usePagedList } from "@/lib/use-paged-list";
import { formatDate } from "@/lib/verify";

/** Whole calendar days from `today` to `validUntil` (both YYYY-MM-DD): no timezone drift. */
function daysLeft(today: string, validUntil: string): number {
  let n = 0;
  let d = today;
  const step = validUntil >= today ? 1 : -1;
  while (d !== validUntil && Math.abs(n) < 4000) {
    d = addDaysToIsoDate(d, step);
    n += step;
  }
  return n;
}

function StatCard({ label, value }: { label: string; value: number }) {
  return (
    <View style={styles.stat}>
      <Text style={styles.statValue}>{value}</Text>
      <Text style={styles.statLabel}>{label}</Text>
    </View>
  );
}

/** Officer expiry view: certificate counts for the officer's district and the expiring-soon list. */
export function ExpiryDashboard() {
  const stats = useAsync(() => api<AdminCertificateStats>("/admin/certificates/stats"));
  const meta = useAsync(getApplicationMeta);
  const { list, error, loading, loadMore, restart } = usePagedList<Certificate>("/admin/certificates/expiring-soon");
  const today = meta.data ? todayInTimezone(meta.data.scheduling.timezone) : null;

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
      {stats.data ? (
        <View style={styles.statRow}>
          <StatCard label="Valid" value={stats.data.valid} />
          <StatCard label="Expiring soon" value={stats.data.expiring_soon} />
          <StatCard label="Expired" value={stats.data.expired} />
          <StatCard label="Revoked" value={stats.data.revoked} />
        </View>
      ) : stats.status === "error" ? (
        <View style={{ gap: 8 }}>
          <Muted>Couldn&apos;t load certificate counts.</Muted>
          <Button label="Try again" variant="secondary" onPress={stats.retry} />
        </View>
      ) : (
        <Muted>Loading counts…</Muted>
      )}
      <Text style={styles.heading}>Expiring soon</Text>
    </View>
  );

  if (!list && loading) return <Loading label="Loading…" />;
  if (!list && error) return <ErrorState message={error} onRetry={restart} />;

  return (
    <Screen scroll={false} hasHeader>
      <FlatList
        data={list?.items ?? []}
        keyExtractor={(c) => c.id}
        refreshing={false}
        onRefresh={() => {
          stats.retry();
          restart();
        }}
        ListHeaderComponent={header}
        ListEmptyComponent={<Empty message="Nothing expiring soon." />}
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
          const days = today ? daysLeft(today, c.valid_until) : null;
          return (
            <Pressable
              onPress={() => openInTab({ pathname: "/certificates/[id]", params: { id: c.id } })}
              style={styles.card}
            >
              <View style={styles.cardTop}>
                <Text style={styles.number}>{c.certificate_number}</Text>
                {days !== null ? (
                  <Text style={[styles.days, days <= 7 && { color: colors.danger }]}>
                    {days === 1 ? "1 day left" : `${days} days left`}
                  </Text>
                ) : null}
              </View>
              <Text style={styles.cardTitle}>{c.organization_name}</Text>
              <Text style={styles.muted}>
                {c.manufacturer} {c.model} · S/N {c.serial_number}
              </Text>
              <Text style={styles.muted}>Valid until {formatDate(c.valid_until)}</Text>
            </Pressable>
          );
        }}
      />
    </Screen>
  );
}

const styles = StyleSheet.create({
  statRow: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  stat: { flexGrow: 1, flexBasis: "45%", backgroundColor: colors.card, borderRadius: 12, padding: 12, borderWidth: 1, borderColor: colors.border },
  statValue: { fontSize: 24, fontWeight: "700", color: colors.text },
  statLabel: { fontSize: 13, color: colors.muted },
  heading: { fontSize: 18, fontWeight: "700", color: colors.text },
  card: { backgroundColor: colors.card, borderRadius: 12, padding: 14, gap: 4, borderWidth: 1, borderColor: colors.border },
  cardTop: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", gap: 8 },
  number: { fontSize: 13, color: colors.muted, fontFamily: "monospace", flexShrink: 1 },
  days: { fontSize: 13, fontWeight: "700", color: "#92400e" },
  cardTitle: { fontSize: 16, fontWeight: "600", color: colors.text },
  muted: { fontSize: 14, color: colors.muted },
});
