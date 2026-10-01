import Link from "next/link";
import type { LucideIcon } from "lucide-react";
import { ClipboardCheck, Landmark, MapPin, ShieldCheck, Building2 } from "lucide-react";

import { SiteFooter } from "@/components/marketing/site-footer";
import { SiteHeader } from "@/components/marketing/site-header";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

interface RoleOption {
  label: string;
  description: string;
  icon: LucideIcon;
}

// Role comes from the account's credentials, not this page — these cards are a navigational
// directory so officers at every level can find their way to the one real login form.
const ROLE_OPTIONS: RoleOption[] = [
  {
    label: "LM Officer",
    description: "Review applications, inspect instruments and approve or reject verifications.",
    icon: ClipboardCheck,
  },
  {
    label: "GATC (Test Centre)",
    description: "Run verifications assigned to a Government Approved Test Centre.",
    icon: ShieldCheck,
  },
  {
    label: "District Admin",
    description: "Oversight, stats and audit logs within a district.",
    icon: Building2,
  },
  {
    label: "State Admin",
    description: "Oversight, stats and audit logs across a state's districts.",
    icon: MapPin,
  },
  {
    label: "Super Admin",
    description: "Platform-wide oversight across every state.",
    icon: Landmark,
  },
];

export default function OfficialLoginPage() {
  return (
    <div className="flex flex-1 flex-col">
      <SiteHeader />

      <main className="flex-1">
        <div className="mx-auto w-full max-w-3xl px-4 py-16">
          <div className="text-center">
            <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">Official Login</h1>
            <p className="mt-2 text-muted-foreground">Select your role to continue to sign in.</p>
          </div>

          <div className="mt-10 grid gap-4 sm:grid-cols-2">
            {ROLE_OPTIONS.map(({ label, description, icon: Icon }) => (
              <Link key={label} href="/login" className="min-h-11 rounded-xl">
                <Card className="h-full transition-colors hover:bg-muted/50">
                  <CardHeader>
                    <div className="flex items-center gap-3">
                      <span className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-accent text-primary">
                        <Icon className="size-5" aria-hidden="true" />
                      </span>
                      <CardTitle>{label}</CardTitle>
                    </div>
                  </CardHeader>
                  <CardContent className="text-sm text-muted-foreground">{description}</CardContent>
                </Card>
              </Link>
            ))}
          </div>

          <p className="mt-10 text-center text-sm text-muted-foreground">
            Running a business?{" "}
            <Link href="/login" className="font-medium text-foreground underline underline-offset-4">
              Merchant Login
            </Link>
          </p>
        </div>
      </main>

      <SiteFooter />
    </div>
  );
}
