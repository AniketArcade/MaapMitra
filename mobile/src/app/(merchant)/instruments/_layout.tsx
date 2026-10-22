import { Stack } from "expo-router";

// Instruments tab: list -> detail -> edit, plus the create form, each with its own header.
export default function InstrumentsStack() {
  return (
    <Stack>
      <Stack.Screen name="index" options={{ title: "Instruments" }} />
      <Stack.Screen name="new" options={{ title: "Register instrument" }} />
      <Stack.Screen name="[id]/index" options={{ title: "Instrument" }} />
      <Stack.Screen name="[id]/edit" options={{ title: "Edit instrument" }} />
    </Stack>
  );
}
