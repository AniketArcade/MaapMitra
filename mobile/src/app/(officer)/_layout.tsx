import { Tabs } from "expo-router";

import { tabIcon } from "@/components/tab-icon";
import { colors } from "@/lib/theme";

// Mirrors OFFICER_NAV. Six entries don't fit a bottom bar: the last three live under "More"
// (a nested stack under /more). UX only.
export default function OfficerTabs() {
  return (
    <Tabs screenOptions={{ headerShown: false, tabBarActiveTintColor: colors.primary }}>
      <Tabs.Screen name="index" options={{ title: "Dashboard", tabBarIcon: tabIcon("home-outline") }} />
      <Tabs.Screen name="applications" options={{ title: "Applications", tabBarIcon: tabIcon("document-text-outline") }} />
      <Tabs.Screen name="certificates" options={{ title: "Certificates", tabBarIcon: tabIcon("ribbon-outline") }} />
      <Tabs.Screen name="more" options={{ title: "More", tabBarIcon: tabIcon("ellipsis-horizontal") }} />
    </Tabs>
  );
}
