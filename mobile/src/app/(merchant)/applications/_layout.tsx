import { Stack } from "expo-router";

// Applications tab: list -> detail, plus the create form, each with its own header.
// Pushing into this tab from elsewhere (withAnchor) keeps the list underneath, so Back reaches it.
export const unstable_settings = { anchor: "index" };

export default function ApplicationsStack() {
  return (
    <Stack>
      <Stack.Screen name="index" options={{ title: "Applications" }} />
      <Stack.Screen name="new" options={{ title: "New application" }} />
      <Stack.Screen name="[id]" options={{ title: "Application" }} />
    </Stack>
  );
}
