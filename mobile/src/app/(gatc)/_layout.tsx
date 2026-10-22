import { Tabs } from "expo-router";

import { tabIcon } from "@/components/tab-icon";
import { colors } from "@/lib/theme";

// Mirrors GATC_NAV: no Instruments (no GATC scope) and no Expiring soon. UX only.
export default function GatcTabs() {
  return (
    <Tabs screenOptions={{ headerShown: false, tabBarActiveTintColor: colors.primary }}>
      <Tabs.Screen name="index" options={{ title: "Dashboard", tabBarIcon: tabIcon("home-outline") }} />
      <Tabs.Screen name="applications" options={{ title: "Applications", tabBarIcon: tabIcon("document-text-outline") }} />
      <Tabs.Screen name="certificates" options={{ title: "Certificates", tabBarIcon: tabIcon("ribbon-outline") }} />
      <Tabs.Screen name="profile" options={{ title: "Profile", tabBarIcon: tabIcon("person-outline") }} />
    </Tabs>
  );
}
