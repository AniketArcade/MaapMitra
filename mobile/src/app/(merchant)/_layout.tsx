import { Tabs } from "expo-router";

import { tabIcon } from "@/components/tab-icon";
import { colors } from "@/lib/theme";

// Mirrors NAV in frontend/components/app-shell.tsx (Business) plus Certificates: the API lets a
// Business list its own certificates even though the web only links them from applications.
// UX only: the backend enforces.
export default function MerchantTabs() {
  return (
    <Tabs screenOptions={{ headerShown: false, tabBarActiveTintColor: colors.primary }}>
      <Tabs.Screen name="index" options={{ title: "Dashboard", tabBarIcon: tabIcon("home-outline") }} />
      <Tabs.Screen name="instruments" options={{ title: "Instruments", tabBarIcon: tabIcon("speedometer-outline") }} />
      <Tabs.Screen name="applications" options={{ title: "Applications", tabBarIcon: tabIcon("document-text-outline") }} />
      <Tabs.Screen name="certificates" options={{ title: "Certificates", tabBarIcon: tabIcon("ribbon-outline") }} />
      <Tabs.Screen name="profile" options={{ title: "Profile", tabBarIcon: tabIcon("person-outline") }} />
    </Tabs>
  );
}
