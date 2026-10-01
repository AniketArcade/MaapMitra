"use client";

import { useRouter } from "next/navigation";
import { Search } from "lucide-react";
import { useState, type FormEvent } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export default function VerifyLookupPage() {
  const router = useRouter();
  const [certificateNumber, setCertificateNumber] = useState("");

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmed = certificateNumber.trim();
    if (!trimmed) return;
    router.push(`/verify/${encodeURIComponent(trimmed)}`);
  }

  return (
    <Card className="w-full max-w-sm">
      <CardHeader>
        <CardTitle className="text-xl">Verify a certificate</CardTitle>
        <CardDescription>
          Scan the QR code on a certificate with your phone&apos;s camera, or enter the certificate
          number below.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={onSubmit} className="grid gap-4" noValidate>
          <div className="grid gap-2">
            <Label htmlFor="certificateNumber">Certificate number</Label>
            <Input
              id="certificateNumber"
              name="certificateNumber"
              placeholder="e.g. CERT-2026-000123"
              value={certificateNumber}
              onChange={(e) => setCertificateNumber(e.target.value)}
              autoComplete="off"
              required
            />
          </div>
          <Button type="submit" className="h-10" disabled={!certificateNumber.trim()}>
            <Search className="size-4" aria-hidden="true" />
            Check validity
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}
