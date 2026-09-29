import Link from "next/link";

import { buttonVariants } from "@/components/ui/button";

export default function Home() {
  return (
    <main className="flex flex-1 flex-col items-center justify-center gap-6 px-4 py-16 text-center">
      <div className="grid max-w-xl gap-3">
        <h1 className="text-3xl font-semibold tracking-tight">Legal Metrology Verification</h1>
        <p className="text-muted-foreground">
          Register weighing and measuring instruments, apply for verification and get a digital
          certificate with a QR code anyone can check.
        </p>
      </div>
      <div className="flex gap-3">
        <Link href="/login" className={buttonVariants({ size: "lg" })}>
          Log in
        </Link>
        <Link href="/register" className={buttonVariants({ size: "lg", variant: "outline" })}>
          Register your business
        </Link>
      </div>
    </main>
  );
}
