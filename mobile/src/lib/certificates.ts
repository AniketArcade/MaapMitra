import { File, Paths } from "expo-file-system";
import * as Sharing from "expo-sharing";
import { Linking } from "react-native";

import { api } from "@/lib/api";

type Signed = { url: string; expires_in: number };

// The signed URL is short-lived (300 s) and fetched on demand: never cached or stored.
function signedPdfUrl(certificateId: string, disposition: "inline" | "attachment"): Promise<Signed> {
  return api<Signed>(`/certificates/${certificateId}/pdf?disposition=${disposition}`);
}

/** Opens the certificate PDF in the system viewer/browser. */
export async function openCertificatePdf(certificateId: string): Promise<void> {
  const { url } = await signedPdfUrl(certificateId, "inline");
  await Linking.openURL(url);
}

/** Downloads the PDF to the cache and opens the share sheet (save, print, send). */
export async function shareCertificatePdf(certificateId: string, certificateNumber: string): Promise<void> {
  const { url } = await signedPdfUrl(certificateId, "attachment");
  const target = new File(Paths.cache, `${certificateNumber}.pdf`);
  if (target.exists) target.delete();
  const file = await File.downloadFileAsync(url, target);
  if (!(await Sharing.isAvailableAsync())) throw new Error("Sharing isn't available on this device.");
  await Sharing.shareAsync(file.uri, { mimeType: "application/pdf", dialogTitle: certificateNumber });
}
