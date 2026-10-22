import { router } from "expo-router";

import { Button, Screen, Title } from "@/components/ui";

export default function More() {
  return (
    <Screen>
      <Title>More</Title>
      <Button label="Instruments" variant="secondary" onPress={() => router.push("/more/instruments")} />
      <Button label="Expiring soon" variant="secondary" onPress={() => router.push("/more/expiring-soon")} />
      <Button label="Profile" variant="secondary" onPress={() => router.push("/more/profile")} />
    </Screen>
  );
}
