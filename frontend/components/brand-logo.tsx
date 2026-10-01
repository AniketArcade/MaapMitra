import { Scale } from "lucide-react";

import { cn } from "cn";

// Single source of truth for the MaapMitra wordmark so it renders identically on the landing
// page, the app sidebar, and every standalone public page (auth, verify).
export function BrandLogo({
  className,
  iconClassName,
  textClassName,
  tone = "light",
}: {
  className?: string;
  iconClassName?: string;
  textClassName?: string;
  tone?: "light" | "dark";
}) {
  return (
    <span className={cn("flex items-center gap-2", className)}>
      <Scale
        className={cn("size-6 shrink-0", tone === "light" ? "text-primary" : "text-sidebar-foreground", iconClassName)}
        aria-hidden="true"
      />
      <span
        className={cn(
          "font-heading text-lg font-semibold tracking-tight",
          tone === "light" ? "text-foreground" : "text-sidebar-foreground",
          textClassName,
        )}
      >
        Maap<span className="text-success">Mitra</span>
      </span>
    </span>
  );
}
