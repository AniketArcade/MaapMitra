import type { Instrument } from "@api-types";
import { router, useLocalSearchParams } from "expo-router";

import { InstrumentForm } from "@/components/instrument-form";
import { ErrorState, Loading, Screen } from "@/components/ui";
import { api, describeError } from "@/lib/api";
import { useAsync } from "@/lib/use-async";

export default function EditInstrument() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const state = useAsync(() => api<Instrument>(`/instruments/${id}`));

  if (!state.data) {
    return state.status === "error" ? (
      <ErrorState message={describeError(new Error())} onRetry={state.retry} />
    ) : (
      <Loading />
    );
  }
  return (
    <Screen hasHeader>
      <InstrumentForm mode="edit" initial={state.data} onSaved={() => router.back()} />
    </Screen>
  );
}
