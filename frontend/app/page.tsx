import Link from "next/link";
import { ArrowRight, BadgeCheck, CalendarClock, FilePlus2, QrCode, ShieldCheck, Store } from "lucide-react";

import { HeroIllustration } from "@/components/marketing/hero-illustration";
import { SiteFooter } from "@/components/marketing/site-footer";
import { SiteHeader } from "@/components/marketing/site-header";
import { buttonVariants } from "@/components/ui/button";
import { cn } from "cn";

const STEPS = [
  {
    icon: FilePlus2,
    title: "Register instrument",
    description: "Businesses add their weighing and measuring instruments to the platform.",
  },
  {
    icon: BadgeCheck,
    title: "Verify & certify",
    description: "An officer inspects the instrument and issues a digital certificate with a QR code.",
  },
  {
    icon: CalendarClock,
    title: "Track validity",
    description: "Certificate expiry is tracked automatically, so re-verification is never missed.",
  },
];

export default function Home() {
  return (
    <div className="flex flex-1 flex-col">
      <SiteHeader />

      <main className="flex-1">
        <section className="relative overflow-hidden">
          <div className="pointer-events-none absolute inset-0 -z-10" aria-hidden="true">
            <div className="absolute inset-0 bg-gradient-to-b from-success/10 via-success/5 to-transparent" />
            <div className="absolute -top-32 -left-32 size-[28rem] rounded-full bg-success/15 blur-3xl" />
            <div className="absolute top-1/3 -right-32 size-[24rem] rounded-full bg-success/10 blur-3xl" />
            <div
              className="absolute inset-0 opacity-[0.07]"
              style={{
                backgroundImage: "radial-gradient(currentColor 1px, transparent 1px)",
                backgroundSize: "20px 20px",
                color: "var(--success)",
              }}
            />
          </div>

          <div className="mx-auto grid w-full max-w-6xl gap-10 px-4 py-16 sm:py-20 lg:grid-cols-2 lg:items-center lg:gap-16">
            <div className="grid gap-6">
              <span className="flex w-fit items-center gap-1.5 rounded-full bg-success/10 px-3 py-1 text-xs font-semibold tracking-wide text-success ring-1 ring-success/20">
                <ShieldCheck className="size-3.5" aria-hidden="true" />
                TRUSTED VERIFICATIONS
              </span>
              <h1 className="text-4xl font-semibold tracking-tight sm:text-5xl">
                Verification <span className="text-foreground">made</span>{" "}
                <span className="text-success">clear.</span>
              </h1>
              <p className="max-w-md text-lg text-muted-foreground">
                Manage instrument verification, certificates and validity with confidence.
              </p>
              <div className="flex flex-wrap items-center gap-5">
                <Link href="/login" className={cn(buttonVariants({ size: "lg" }), "rounded-full gap-2")}>
                  Merchant Login
                  <ArrowRight className="size-4" aria-hidden="true" />
                </Link>
                <Link
                  href="/how-it-works"
                  className="text-sm font-semibold text-primary underline-offset-4 hover:underline"
                >
                  How it works →
                </Link>
              </div>
            </div>

            <HeroIllustration />
          </div>
        </section>

        <section className="mx-auto grid w-full max-w-6xl gap-4 px-4 pb-16 sm:grid-cols-2">
          <Link
            href="/verify"
            className="group flex items-center justify-between gap-4 rounded-2xl bg-success/10 p-6 ring-1 ring-success/20 transition-colors hover:bg-success/15"
          >
            <div className="flex items-center gap-4">
              <span className="flex size-11 shrink-0 items-center justify-center rounded-xl bg-success/15 text-success">
                <QrCode className="size-6" aria-hidden="true" />
              </span>
              <div>
                <p className="font-semibold">Scan QR & Verify</p>
                <p className="text-sm text-muted-foreground">Public certificate validity check</p>
              </div>
            </div>
            <span className="text-muted-foreground transition-transform group-hover:translate-x-0.5">
              →
            </span>
          </Link>

          <Link
            href="/login"
            className="group flex items-center justify-between gap-4 rounded-2xl bg-warning/10 p-6 ring-1 ring-warning/20 transition-colors hover:bg-warning/15"
          >
            <div className="flex items-center gap-4">
              <span className="flex size-11 shrink-0 items-center justify-center rounded-xl bg-warning/20 text-warning-foreground">
                <Store className="size-6" aria-hidden="true" />
              </span>
              <div>
                <p className="font-semibold">Merchant Login</p>
                <p className="text-sm text-muted-foreground">Register instruments and manage verifications</p>
              </div>
            </div>
            <span className="text-muted-foreground transition-transform group-hover:translate-x-0.5">
              →
            </span>
          </Link>
        </section>

        <section className="border-t border-border bg-muted/30">
          <div className="mx-auto w-full max-w-6xl px-4 py-16 text-center">
            <h2 className="text-2xl font-semibold tracking-tight sm:text-3xl">
              How Maap<span className="text-success">Mitra</span> helps
            </h2>
            <div className="mx-auto mt-3 h-1 w-14 rounded-full bg-success" />

            <div className="mt-12 grid gap-10 sm:grid-cols-3 sm:gap-6">
              {STEPS.map(({ icon: Icon, title, description }, i) => (
                <div key={title} className="relative flex flex-col items-center gap-3">
                  {i < STEPS.length - 1 ? (
                    <span
                      className="absolute top-8 left-[calc(50%+2.5rem)] hidden h-px w-[calc(100%-5rem)] bg-border sm:block"
                      aria-hidden="true"
                    />
                  ) : null}
                  <span className="flex size-16 items-center justify-center rounded-full bg-accent text-primary">
                    <Icon className="size-7" aria-hidden="true" />
                  </span>
                  <p className="font-semibold">{title}</p>
                  <p className="max-w-[16rem] text-sm text-muted-foreground">{description}</p>
                </div>
              ))}
            </div>
          </div>
        </section>
      </main>

      <SiteFooter />
    </div>
  );
}
