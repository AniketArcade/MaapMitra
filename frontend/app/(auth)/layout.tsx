import type { ReactNode } from "react";

export default function AuthLayout({ children }: { children: ReactNode }) {
  return (
    <main className="flex flex-1 items-center justify-center bg-muted/40 px-4 py-10">{children}</main>
  );
}
