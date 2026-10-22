import { router } from "expo-router";

import { InstrumentList } from "@/components/instrument-list";

// Read-only view of the officer's jurisdiction (the backend scopes the list).
export default function OfficerInstruments() {
  return <InstrumentList onOpen={(id) => router.push({ pathname: "/more/instruments/[id]", params: { id } })} />;
}
