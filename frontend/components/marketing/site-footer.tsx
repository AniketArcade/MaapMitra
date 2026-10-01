import Link from "next/link";

import { BrandLogo } from "@/components/brand-logo";

export function SiteFooter() {
  return (
    <footer className="border-t border-border">
      <div className="mx-auto flex w-full max-w-6xl flex-col items-center gap-3 px-4 py-6 text-sm text-muted-foreground sm:flex-row sm:justify-between">
        <span className="flex items-center gap-2">
          <BrandLogo textClassName="text-sm font-medium text-muted-foreground" iconClassName="size-4 text-muted-foreground" />
          <span>— Legal Metrology verification &amp; digital certification</span>
        </span>
        <nav className="flex items-center gap-4">
          <Link href="/how-it-works" className="hover:text-foreground">
            How it Works
          </Link>
          <Link href="/support" className="hover:text-foreground">
            Support
          </Link>
          <Link href="/verify" className="hover:text-foreground">
            Verify a certificate
          </Link>
        </nav>
      </div>
    </footer>
  );
}
