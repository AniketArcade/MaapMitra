import Link from "next/link";
import type { ReactNode } from "react";

import { BrandLogo } from "@/components/brand-logo";

// Public, no AppShell: no header nav, no auth guard to skip past. Same centered-card shape as
// the equally-public (auth) layout. Covers both /verify (lookup form) and /verify/[certificateNumber].
export default function VerifyLayout({ children }: { children: ReactNode }) {
  return (
    <main className="flex flex-1 flex-col items-center justify-center gap-6 bg-muted/40 px-4 py-10">
      <Link href="/">
        <BrandLogo />
      </Link>
      {children}
    </main>
  );
}
