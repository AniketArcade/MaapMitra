import { Stack } from "expo-router";

// "More" tab: a nested stack so the extra officer screens have their own unique paths
// (/more/instruments, ...) instead of colliding with other roles' routes.
// Pushing into this tab from elsewhere (withAnchor) keeps the list underneath, so Back reaches it.
export const unstable_settings = { anchor: "index" };

export default function MoreStack() {
  return (
    <Stack>
      <Stack.Screen name="index" options={{ headerShown: false }} />
      <Stack.Screen name="instruments" options={{ title: "Instruments" }} />
      <Stack.Screen name="expiring-soon" options={{ title: "Expiring soon" }} />
      <Stack.Screen name="profile" options={{ title: "Profile" }} />
    </Stack>
  );
}
