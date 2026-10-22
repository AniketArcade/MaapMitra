import { View } from "react-native";

import { Button, Muted, Screen, Title } from "@/components/ui";
import { useAuth } from "@/lib/auth";

export function ProfileView() {
  const { user, logout } = useAuth();
  return (
    <Screen>
      <Title>Profile</Title>
      {user ? (
        <View style={{ gap: 4 }}>
          <Muted>{user.full_name}</Muted>
          <Muted>{user.email}</Muted>
          <Muted>Role: {user.role}</Muted>
          {user.organization_name ? <Muted>Organization: {user.organization_name}</Muted> : null}
          {user.state_code ? <Muted>Region: {user.state_code}{user.district_code ? ` / ${user.district_code}` : ""}</Muted> : null}
        </View>
      ) : null}
      <Button label="Log out" variant="secondary" onPress={() => void logout()} />
    </Screen>
  );
}
