"use client";

import { useRouter } from "next/navigation";
import { useEffect, type ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { useAuth } from "@/lib/auth";

// UX guard only. The backend enforces every permission.
export default function DashboardLayout({ children }: { children: ReactNode }) {
  const { user, status, logout } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (status === "anonymous") router.replace("/login?next=/dashboard");
  }, [status, router]);

  if (status !== "authenticated" || !user) {
    return (
      <main className="flex flex-1 items-center justify-center text-sm text-muted-foreground">
        Loading…
      </main>
    );
  }

  return (
    <div className="flex flex-1 flex-col">
      <header className="flex items-center justify-between gap-4 border-b px-4 py-3">
        <span className="font-semibold">Legal Metrology</span>
        <div className="flex items-center gap-3 text-sm">
          <span className="hidden text-muted-foreground sm:inline">{user.email}</span>
          <Button variant="outline" size="sm" onClick={() => void logout()}>
            Log out
          </Button>
        </div>
      </header>
      <main className="mx-auto w-full max-w-4xl flex-1 px-4 py-6">{children}</main>
    </div>
  );
}
