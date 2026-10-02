"use client";

import { useRouter } from "next/navigation";
import { Search } from "lucide-react";
import { useCallback, useState, type FormEvent } from "react";

import { QrScannerCard } from "@/components/verify/qr-scanner";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";
import { parseCertificateNumberFromScan } from "@/lib/qr";

export default function VerifyLookupPage() {
  const router = useRouter();
  const [certificateNumber, setCertificateNumber] = useState("");

  const goToCertificate = useCallback(
    (raw: string) => {
      const trimmed = raw.trim();
      if (!trimmed) return;
      router.push(`/verify/${encodeURIComponent(trimmed)}`);
    },
    [router],
  );

  const handleDecode = useCallback(
    (raw: string) => goToCertificate(parseCertificateNumberFromScan(raw)),
    [goToCertificate],
  );

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    goToCertificate(certificateNumber);
  }

  return (
    <Card className="w-full max-w-sm">
      <CardHeader>
        <CardTitle className="text-xl">Verify a certificate</CardTitle>
        <CardDescription>Point your camera at the QR code on a certificate.</CardDescription>
      </CardHeader>
      <CardContent className="grid gap-5">
        <QrScannerCard onDecode={handleDecode} />

        <div className="flex items-center gap-3">
          <Separator className="flex-1" />
          <span className="text-xs text-muted-foreground">or enter manually</span>
          <Separator className="flex-1" />
        </div>

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
