import type { Application, ApplicationStats, Instrument, Page } from "@api-types";
import { router } from "expo-router";
import { Text, View } from "react-native";

import { Chip, Section } from "@/components/section";
import { Button, Muted, Screen, Title } from "@/components/ui";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { getApplicationMeta, labelFor } from "@/lib/meta";
import { colors } from "@/lib/theme";
import { useAsync } from "@/lib/use-async";

function ApplicationRow({ a, statusLabel }: { a: Application; statusLabel: string }) {
  return (
    <View style={{ gap: 2 }}>
      <Text style={{ fontWeight: "600", color: colors.text }}>{a.application_number}</Text>
      <Muted>
        {statusLabel} · {a.instrument.manufacturer} {a.instrument.model} · S/N {a.instrument.serial_number}
      </Muted>
    </View>
  );
}

export default function MerchantDashboard() {
  const { user } = useAuth();
  const instruments = useAsync(() => api<Page<Instrument>>("/instruments?page_size=1").then((p) => p.total));
  const stats = useAsync(() => api<ApplicationStats>("/applications/stats"));
  const drafts = useAsync(() => api<Page<Application>>("/applications?status=DRAFT&page_size=5"));
  const recent = useAsync(() => api<Page<Application>>("/applications?page_size=5"));
  const meta = useAsync(getApplicationMeta);
  const statusLabel = (s: string) => labelFor(meta.data?.statuses, s);

  return (
    <Screen>
      <Title>{user?.organization_name ?? "Dashboard"}</Title>
      <Muted>Business dashboard</Muted>

      <Section title="Instruments" state={instruments} errorMessage="Couldn't load your instruments.">
        {(total) => (
          <View style={{ gap: 8 }}>
            <Text style={{ color: colors.text }}>
              {total === 0 ? "No instruments registered yet." : `${total} instrument${total === 1 ? "" : "s"}`}
            </Text>
            <Button
              label={total === 0 ? "Register your first instrument" : "Register instrument"}
              variant={total === 0 ? "primary" : "secondary"}
              onPress={() => router.push("/instruments/new")}
            />
          </View>
        )}
      </Section>

      <Section title="Applications" state={stats} errorMessage="Couldn't load application stats.">
        {({ total, by_status }) =>
          total === 0 ? (
            <Muted>No applications yet. Open an instrument to apply for verification.</Muted>
          ) : (
            <View style={{ gap: 8 }}>
              <Text style={{ color: colors.text }}>
                {total} application{total === 1 ? "" : "s"}
              </Text>
              <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 8 }}>
                {/* meta.statuses is served in lifecycle order (DRAFT ... CERTIFICATE_ISSUED) */}
                {(meta.data?.statuses ?? [])
                  .filter((s) => by_status[s.value])
                  .map((s) => (
                    <Chip key={s.value}>
                      {by_status[s.value]} {s.label}
                    </Chip>
                  ))}
              </View>
            </View>
          )
        }
      </Section>

      <Section title="Needs your attention" state={drafts} errorMessage="Couldn't load drafts.">
        {(page) =>
          page.items.length === 0 ? (
            <Muted>Nothing waiting on you.</Muted>
          ) : (
            <View style={{ gap: 10 }}>
              <Muted>Drafts: upload documents and submit.</Muted>
              {page.items.map((a) => (
                <ApplicationRow key={a.id} a={a} statusLabel={statusLabel(a.status)} />
              ))}
            </View>
          )
        }
      </Section>

      <Section title="Recent applications" state={recent} errorMessage="Couldn't load recent applications.">
        {(page) =>
          page.items.length === 0 ? (
            <Muted>No applications yet.</Muted>
          ) : (
            <View style={{ gap: 10 }}>
              {page.items.map((a) => (
                <ApplicationRow key={a.id} a={a} statusLabel={statusLabel(a.status)} />
              ))}
            </View>
          )
        }
      </Section>
    </Screen>
  );
}
