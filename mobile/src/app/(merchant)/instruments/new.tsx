import { router } from "expo-router";

import { InstrumentForm } from "@/components/instrument-form";
import { Screen } from "@/components/ui";

export default function NewInstrument() {
  return (
    <Screen hasHeader>
      <InstrumentForm
        mode="create"
        onSaved={(i) => router.replace({ pathname: "/instruments/[id]", params: { id: i.id } })}
      />
    </Screen>
  );
}
