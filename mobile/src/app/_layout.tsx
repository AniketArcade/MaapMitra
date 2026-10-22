import { Stack } from "expo-router";
import { StatusBar } from "expo-status-bar";

import { Button, ErrorText, Loading, Screen } from "@/components/ui";
import { AuthProvider, useAuth } from "@/lib/auth";

function RootStack() {
  const { status, user, retry } = useAuth();

  if (status === "loading") return <Loading label="Starting MaapMitra…" />;
  if (status === "offline") {
    return (
      <Screen>
        <ErrorText>Can&apos;t reach the server. Your session is kept; check your connection.</ErrorText>
        <Button label="Try again" onPress={retry} />
      </Screen>
    );
  }

  const role = status === "authenticated" ? user?.role : undefined;
  return (
    <Stack screenOptions={{ headerShown: false }}>
      <Stack.Protected guard={status === "anonymous"}>
        <Stack.Screen name="(auth)" />
      </Stack.Protected>
      <Stack.Protected guard={role === "BUSINESS"}>
        <Stack.Screen name="(merchant)" />
      </Stack.Protected>
      <Stack.Protected guard={role === "LM_OFFICER"}>
        <Stack.Screen name="(officer)" />
      </Stack.Protected>
      <Stack.Protected guard={role === "GATC"}>
        <Stack.Screen name="(gatc)" />
      </Stack.Protected>
      {/* Field inspection: full screen (no tabs), for the roles that inspect. */}
      <Stack.Protected guard={role === "LM_OFFICER" || role === "GATC"}>
        <Stack.Screen name="inspection/[id]" options={{ headerShown: true, title: "Field inspection" }} />
      </Stack.Protected>
      {/* Public: reachable signed in or out (QR verification needs no login). */}
      <Stack.Screen name="verify" options={{ headerShown: true, title: "Verify a certificate" }} />
    </Stack>
  );
}

export default function RootLayout() {
  return (
    <AuthProvider>
      <StatusBar style="auto" />
      <RootStack />
    </AuthProvider>
  );
}
