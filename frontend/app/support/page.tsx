import { LifeBuoy } from "lucide-react";

import { SiteFooter } from "@/components/marketing/site-footer";
import { SiteHeader } from "@/components/marketing/site-header";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

const FAQS = [
  {
    question: "How do I register an instrument?",
    answer: "Log in as a business, go to Instruments, and use Register instrument.",
  },
  {
    question: "How do I apply for verification?",
    answer: "Open a registered instrument and start an application, then upload the required documents.",
  },
  {
    question: "How do I check if a certificate is valid?",
    answer: "Use Scan QR & Verify on the home page, or open the link printed on the certificate's QR code. No login is required.",
  },
  {
    question: "I'm an LM Officer, GATC or admin — where do I sign in?",
    answer: "Use Official Login on the home page and select your role, then sign in with your account.",
  },
];

// ASSUMPTION: no live support channel (email/phone/ticketing) is wired up yet for this MVP.
export default function SupportPage() {
  return (
    <div className="flex flex-1 flex-col">
      <SiteHeader />

      <main className="flex-1">
        <div className="mx-auto w-full max-w-2xl px-4 py-16">
          <div className="text-center">
            <span className="mx-auto flex size-12 items-center justify-center rounded-full bg-accent text-primary">
              <LifeBuoy className="size-6" aria-hidden="true" />
            </span>
            <h1 className="mt-4 text-2xl font-semibold tracking-tight sm:text-3xl">Support</h1>
            <p className="mt-2 text-muted-foreground">
              Answers to common questions. A direct support channel is coming soon.
            </p>
          </div>

          <div className="mt-10 grid gap-4">
            {FAQS.map(({ question, answer }) => (
              <Card key={question}>
                <CardHeader>
                  <CardTitle className="text-base">{question}</CardTitle>
                </CardHeader>
                <CardContent className="text-sm text-muted-foreground">{answer}</CardContent>
              </Card>
            ))}
          </div>
        </div>
      </main>

      <SiteFooter />
    </div>
  );
}
