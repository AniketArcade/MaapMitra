import { Stack } from "expo-router";

// "More" tab: a nested stack so the extra officer screens have their own unique paths
// (/more/instruments, ...) instead of colliding with other roles' routes.
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
