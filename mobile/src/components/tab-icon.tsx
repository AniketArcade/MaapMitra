import { Ionicons } from "@expo/vector-icons";
import type { ColorValue } from "react-native";

type IconName = React.ComponentProps<typeof Ionicons>["name"];

/** Tab bar icon factory: `options={{ tabBarIcon: tabIcon("home-outline") }}`. */
export function tabIcon(name: IconName) {
  return function TabIcon({ color, size }: { color: ColorValue; size: number }) {
    // The navigator always passes a concrete tint string; ColorValue is only wider in the types.
    return <Ionicons name={name} color={color as string} size={size} />;
  };
}
