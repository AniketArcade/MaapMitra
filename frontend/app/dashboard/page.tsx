"use client";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useAuth } from "@/lib/auth";
import { ADMIN_ROLES, type User } from "@/lib/types";

function RoleCard({ user }: { user: User }) {
  if (user.role === "BUSINESS") {
    return (
      <Card>
        <CardHeader>
          <CardTitle>{user.organization_name}</CardTitle>
          <CardDescription>Business dashboard</CardDescription>
        </CardHeader>
        <CardContent className="text-sm text-muted-foreground">
          Instruments, applications and certificates will appear here.
        </CardContent>
      </Card>
    );
  }
  if (user.role === "LM_OFFICER") {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Officer dashboard</CardTitle>
          <CardDescription>
            Jurisdiction: {user.state_code} / {user.district_code}
          </CardDescription>
        </CardHeader>
        <CardContent className="text-sm text-muted-foreground">
          Your document reviews and inspections will appear here.
        </CardContent>
      </Card>
    );
  }
  if (ADMIN_ROLES.includes(user.role)) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Admin dashboard</CardTitle>
          <CardDescription>
            Scope: {user.state_code ?? "All states"}
            {user.district_code ? ` / ${user.district_code}` : ""}
          </CardDescription>
        </CardHeader>
        <CardContent className="text-sm text-muted-foreground">
          Statistics, users and audit logs will appear here.
        </CardContent>
      </Card>
    );
  }
  return (
    <Card>
      <CardHeader>
        <CardTitle>GATC dashboard</CardTitle>
        <CardDescription>{user.organization_name}</CardDescription>
      </CardHeader>
      <CardContent className="text-sm text-muted-foreground">
        Assigned verifications will appear here.
      </CardContent>
    </Card>
  );
}

export default function DashboardPage() {
  const { user } = useAuth();
  if (!user) return null;
  return (
    <div className="grid gap-6">
      <h1 className="text-2xl font-semibold">
        Welcome, {user.full_name} <span className="text-base font-normal text-muted-foreground">({user.role})</span>
      </h1>
      <RoleCard user={user} />
    </div>
  );
}
