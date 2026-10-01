import Link from "next/link";
import type { LucideIcon } from "lucide-react";
import {
  BadgeCheck,
  CalendarCheck,
  ClipboardCheck,
  FilePlus2,
  FileSearch,
  QrCode,
  Store,
} from "lucide-react";

import { SiteFooter } from "@/components/marketing/site-footer";
import { SiteHeader } from "@/components/marketing/site-header";
import { buttonVariants } from "@/components/ui/button";

interface LifecycleStep {
  icon: LucideIcon;
  title: string;
  description: string;
}

const STEPS: LifecycleStep[] = [
  {
    icon: FilePlus2,
    title: "Register instrument",
    description: "A business registers a weighing or measuring instrument with its details and location.",
  },
  {
    icon: FileSearch,
    title: "Apply & upload documents",
    description: "The business applies for verification and uploads the required supporting documents.",
  },
  {
    icon: ClipboardCheck,
    title: "Document review",
    description: "An LM Officer reviews the application and documents before scheduling an inspection.",
  },
  {
    icon: CalendarCheck,
    title: "Schedule & inspect",
    description:
      "The verification is scheduled and carried out in the field (or at a test centre), with a checklist and measurements.",
  },
  {
    icon: BadgeCheck,
    title: "Approve & certify",
    description: "On approval, a digital certificate is issued with a QR code for instant verification.",
  },
  {
    icon: QrCode,
    title: "Public verification & expiry",
    description:
      "Anyone can scan the QR code to confirm a certificate is valid. Expiry is tracked so re-verification happens on time.",
  },
];

export default function HowItWorksPage() {
  return (
    <div className="flex flex-1 flex-col">
      <SiteHeader />

      <main className="flex-1">
        <div className="mx-auto w-full max-w-3xl px-4 py-16">
          <div className="text-center">
            <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">How MaapMitra works</h1>
            <p className="mt-2 text-muted-foreground">
              A digital lifecycle for Legal Metrology instrument verification. Physical verification
              stays a field activity — MaapMitra digitizes the workflow around it.
            </p>
          </div>

          <ol className="mt-12 grid gap-8">
            {STEPS.map(({ icon: Icon, title, description }, i) => (
              <li key={title} className="flex gap-4">
                <div className="flex flex-col items-center">
                  <span className="flex size-10 shrink-0 items-center justify-center rounded-full bg-accent font-semibold text-primary">
                    {i + 1}
                  </span>
                  {i < STEPS.length - 1 ? <span className="mt-2 w-px flex-1 bg-border" /> : null}
                </div>
                <div className="pb-2">
                  <div className="flex items-center gap-2">
                    <Icon className="size-4 text-primary" aria-hidden="true" />
                    <p className="font-semibold">{title}</p>
                  </div>
                  <p className="mt-1 text-sm text-muted-foreground">{description}</p>
                </div>
              </li>
            ))}
          </ol>

          <div className="mt-6 flex flex-wrap justify-center gap-4">
            <Link href="/login" className={buttonVariants({ size: "lg" })}>
              <Store className="size-4" aria-hidden="true" />
              Merchant Login
            </Link>
            <Link href="/verify" className={buttonVariants({ variant: "outline", size: "lg" })}>
              <QrCode className="size-4" aria-hidden="true" />
              Verify a certificate
            </Link>
          </div>
        </div>
      </main>

      <SiteFooter />
    </div>
  );
}
