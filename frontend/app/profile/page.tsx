"use client";

import { LogOut } from "lucide-react";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useAuth } from "@/lib/auth";
import { getInstrumentMeta, regionLabel } from "@/lib/meta";
import type { InstrumentMeta } from "@/lib/types";

const ROLE_LABELS: Record<string, string> = {
  SUPER_ADMIN: "Super Admin",
  STATE_ADMIN: "State Admin",
  DISTRICT_ADMIN: "District Admin",
  LM_OFFICER: "LM Officer",
  GATC: "GATC (test centre)",
  BUSINESS: "Business",
};

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div className="grid gap-1">
      <dt className="text-sm text-muted-foreground">{label}</dt>
      <dd className="text-sm font-medium">{value}</dd>
    </div>
  );
}

export default function ProfilePage() {
  const { user, logout } = useAuth();
  // Only needed to turn an official's raw state/district codes into display names (regionLabel
  // falls back to the raw codes while this is still loading or if it fails to load).
  const [meta, setMeta] = useState<InstrumentMeta | null>(null);

  useEffect(() => {
    getInstrumentMeta().then(setMeta, () => setMeta(null));
  }, []);

  if (!user) return null;

  const jurisdiction =
    user.state_code && user.district_code
      ? regionLabel(meta, user.state_code, user.district_code)
      : null;

  return (
    <div className="grid gap-6">
      <h1 className="text-2xl font-semibold">Profile</h1>
      <Card className="max-w-xl">
        <CardHeader>
          <CardTitle>{user.full_name}</CardTitle>
          <CardDescription>{ROLE_LABELS[user.role] ?? user.role}</CardDescription>
        </CardHeader>
        <CardContent>
          <dl className="grid gap-4 sm:grid-cols-2">
            <Field label="Email" value={user.email} />
            {user.organization_name ? (
              <Field label="Organization" value={user.organization_name} />
            ) : null}
            {jurisdiction ? <Field label="Jurisdiction" value={jurisdiction} /> : null}
          </dl>
        </CardContent>
      </Card>
      <div>
        <Button variant="outline" onClick={() => void logout()}>
          <LogOut className="size-4" aria-hidden="true" />
          Log out
        </Button>
      </div>
    </div>
  );
}
