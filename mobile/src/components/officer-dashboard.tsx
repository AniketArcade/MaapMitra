import type { Application, ApplicationStats, Instrument, Page } from "@api-types";
import { router } from "expo-router";
import { Text, View } from "react-native";

import { ApplicationRow } from "@/components/application-row";
import { Chip, Section } from "@/components/section";
import { Button, Muted, Screen, Title } from "@/components/ui";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { getApplicationMeta, labelFor } from "@/lib/meta";
import { colors } from "@/lib/theme";
import { useAsync } from "@/lib/use-async";

type Bucket = { status: string; title: string; hint: string; sort?: string };

// What needs the officer's attention, in workflow order (mirrors the web OfficerDashboard).
const OFFICER_BUCKETS: Bucket[] = [
  { status: "SUBMITTED", title: "Waiting for review", hint: "Start document review" },
  { status: "DOCUMENT_REVIEW", title: "In document review", hint: "Check documents, then schedule" },
  { status: "SCHEDULED", title: "Upcoming inspections", hint: "Soonest first", sort: "scheduled_asc" },
  { status: "INSPECTION", title: "Inspections in progress", hint: "Continue inspection", sort: "scheduled_asc" },
];

function BucketSection({ bucket }: { bucket: Bucket }) {
  const sort = bucket.sort ? `&sort=${bucket.sort}` : "";
  const state = useAsync(() =>
    api<Page<Application>>(`/applications?status=${bucket.status}${sort}&page_size=5`),
  );
  const meta = useAsync(getApplicationMeta);
  return (
    <Section title={bucket.title} state={state} errorMessage={`Couldn't load ${bucket.title.toLowerCase()}.`}>
      {(page) =>
        page.items.length === 0 ? (
          <Muted>Nothing here.</Muted>
        ) : (
          <View style={{ gap: 10 }}>
            <Muted>
              {bucket.hint}
              {page.total > page.items.length ? ` · ${page.total} in total` : ""}
            </Muted>
            {page.items.map((a) => (
              <ApplicationRow
                key={a.id}
                a={a}
                statusLabel={labelFor(meta.data?.statuses, a.status)}
                extra={a.scheduled_date ? `on ${a.scheduled_date}` : undefined}
              />
            ))}
          </View>
        )
      }
    </Section>
  );
}

export function OfficerDashboard() {
  const { user } = useAuth();
  const instruments = useAsync(() => api<Page<Instrument>>("/instruments?page_size=1").then((p) => p.total));
  const stats = useAsync(() => api<ApplicationStats>("/applications/stats"));
  const meta = useAsync(getApplicationMeta);

  return (
    <Screen>
      <Title>Officer dashboard</Title>
      <Muted>
        Jurisdiction: {user?.state_code} / {user?.district_code}
      </Muted>

      <Section title="Instruments" state={instruments} errorMessage="Couldn't load instruments.">
        {(total) => (
          <View style={{ gap: 8 }}>
            <Text style={{ color: colors.text }}>
              {total} instrument{total === 1 ? "" : "s"} in your district
            </Text>
            <Button label="View instruments" variant="secondary" onPress={() => router.push("/more/instruments")} />
          </View>
        )}
      </Section>

      <Section title="Applications" state={stats} errorMessage="Couldn't load application stats.">
        {({ total, by_status }) =>
          total === 0 ? (
            <Muted>No applications in your district yet.</Muted>
          ) : (
            <View style={{ gap: 8 }}>
              <Text style={{ color: colors.text }}>
                {total} application{total === 1 ? "" : "s"}
              </Text>
              <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 8 }}>
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

      {OFFICER_BUCKETS.map((b) => (
        <BucketSection key={b.status} bucket={b} />
      ))}
    </Screen>
  );
}
