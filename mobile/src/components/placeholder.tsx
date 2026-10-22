import { Muted, Screen, Title } from "@/components/ui";
import { useAuth } from "@/lib/auth";

/** Stand-in for screens built in later phases (see appguide.md). */
export function PlaceholderScreen({ title, phase }: { title: string; phase: string }) {
  return (
    <Screen>
      <Title>{title}</Title>
      <Muted>Coming in {phase}.</Muted>
    </Screen>
  );
}

export function DashboardPlaceholder() {
  const { user } = useAuth();
  return (
    <Screen>
      <Title>Dashboard</Title>
      <Muted>
        Signed in as {user?.full_name} ({user?.role})
        {user?.organization_name ? ` · ${user.organization_name}` : ""}
      </Muted>
      <Muted>Dashboard content arrives in a later phase.</Muted>
    </Screen>
  );
}
