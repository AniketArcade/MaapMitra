import type { Application } from "@api-types";
import { Pressable, Text } from "react-native";

import { Muted } from "@/components/ui";
import { openInTab } from "@/lib/nav";
import { colors } from "@/lib/theme";

/** Tappable application summary used on dashboards; opens the detail inside the Applications tab. */
export function ApplicationRow({ a, statusLabel, extra }: { a: Application; statusLabel: string; extra?: string }) {
  return (
    <Pressable
      onPress={() => openInTab({ pathname: "/applications/[id]", params: { id: a.id } })}
      style={{ gap: 2 }}
    >
      <Text style={{ fontWeight: "600", color: colors.text }}>{a.application_number}</Text>
      <Muted>
        {statusLabel}
        {extra ? ` · ${extra}` : ""} · {a.instrument.manufacturer} {a.instrument.model} · S/N {a.instrument.serial_number}
      </Muted>
    </Pressable>
  );
}
