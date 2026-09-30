import type { ReactNode } from "react";

// Public, no AppShell: no header nav, no auth guard to skip past. Same centered-card shape as
// the equally-public (auth) layout.
export default function VerifyLayout({ children }: { children: ReactNode }) {
  return (
    <main className="flex flex-1 items-center justify-center bg-muted/40 px-4 py-10">{children}</main>
  );
}
