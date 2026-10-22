import { router } from "expo-router";

import { InstrumentList } from "@/components/instrument-list";

export default function Instruments() {
  return <InstrumentList canCreate onOpen={(id) => router.push({ pathname: "/instruments/[id]", params: { id } })} />;
}
