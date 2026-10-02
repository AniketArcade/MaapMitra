"use client";

import { Camera, CameraOff, ScanLine } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import QrScanner from "qr-scanner";

type Status = "starting" | "scanning" | "denied" | "unsupported";

export function QrScannerCard({ onDecode }: { onDecode: (raw: string) => void }) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const scannerRef = useRef<QrScanner | null>(null);
  const decodedRef = useRef(false);
  const onDecodeRef = useRef(onDecode);
  const [status, setStatus] = useState<Status>("starting");

  useEffect(() => {
    onDecodeRef.current = onDecode;
  }, [onDecode]);

  useEffect(() => {
    let cancelled = false;

    async function start() {
      const hasCamera = await QrScanner.hasCamera();
      if (cancelled) return;
      if (!hasCamera || !videoRef.current) {
        setStatus("unsupported");
        return;
      }

      const scanner = new QrScanner(
        videoRef.current,
        (result) => {
          if (decodedRef.current) return;
          decodedRef.current = true;
          scanner.stop();
          onDecodeRef.current(result.data);
        },
        {
          preferredCamera: "environment",
          highlightScanRegion: true,
          highlightCodeOutline: true,
        },
      );
      scannerRef.current = scanner;

      try {
        await scanner.start();
        if (!cancelled) setStatus("scanning");
      } catch {
        if (!cancelled) setStatus("denied");
      }
    }

    start();

    return () => {
      cancelled = true;
      scannerRef.current?.stop();
      scannerRef.current?.destroy();
      scannerRef.current = null;
    };
  }, []);

  return (
    <div className="grid gap-2">
      <div className="relative aspect-square w-full overflow-hidden rounded-2xl bg-muted ring-1 ring-border">
        <video ref={videoRef} className="size-full object-cover" muted playsInline />

        {status !== "scanning" ? (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 bg-muted px-6 text-center">
            {status === "starting" ? (
              <>
                <Camera className="size-8 text-muted-foreground" aria-hidden="true" />
                <p className="text-sm text-muted-foreground">Requesting camera access…</p>
              </>
            ) : (
              <>
                <CameraOff className="size-8 text-muted-foreground" aria-hidden="true" />
                <p className="text-sm text-muted-foreground">
                  {status === "denied"
                    ? "Camera access was denied. Enter the certificate number below instead."
                    : "No camera available. Enter the certificate number below instead."}
                </p>
              </>
            )}
          </div>
        ) : null}
      </div>

      {status === "scanning" ? (
        <p className="flex items-center justify-center gap-1.5 text-xs text-muted-foreground">
          <ScanLine className="size-3.5" aria-hidden="true" />
          Point your camera at the certificate&apos;s QR code
        </p>
      ) : null}
    </div>
  );
}
