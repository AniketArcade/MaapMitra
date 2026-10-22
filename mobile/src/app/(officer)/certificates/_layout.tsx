import { Stack } from "expo-router";

// Pushing into this tab from elsewhere (withAnchor) keeps the list underneath, so Back reaches it.
export const unstable_settings = { anchor: "index" };

export default function OfficerCertificatesStack() {
  return (
    <Stack>
      <Stack.Screen name="index" options={{ title: "Certificates" }} />
      <Stack.Screen name="[id]" options={{ title: "Certificate" }} />
    </Stack>
  );
}
