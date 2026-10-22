import type { DocumentOut } from "@api-types";
import * as DocumentPicker from "expo-document-picker";
import { File } from "expo-file-system";
import { ImageManipulator, SaveFormat } from "expo-image-manipulator";
import * as ImagePicker from "expo-image-picker";

import { api } from "@/lib/api";

export type PickedFile = { uri: string; name: string; type: string };

// Phone photos are routinely larger than the server's 10 MiB cap, so they are resized and
// re-encoded as JPEG on the device before upload.
const MAX_EDGE = 2000;
const JPEG_QUALITY = 0.7;

async function compressImage(asset: ImagePicker.ImagePickerAsset): Promise<PickedFile> {
  const context = ImageManipulator.manipulate(asset.uri);
  if (Math.max(asset.width, asset.height) > MAX_EDGE) {
    context.resize(asset.width >= asset.height ? { width: MAX_EDGE } : { height: MAX_EDGE });
  }
  const rendered = await context.renderAsync();
  const saved = await rendered.saveAsync({ format: SaveFormat.JPEG, compress: JPEG_QUALITY });
  return { uri: saved.uri, name: `photo-${Date.now()}.jpg`, type: "image/jpeg" };
}

/** Returns null when the user cancels. Throws an Error with a user-facing message on failure. */
export async function pickPhoto(source: "camera" | "library"): Promise<PickedFile | null> {
  if (source === "camera") {
    const permission = await ImagePicker.requestCameraPermissionsAsync();
    if (!permission.granted) {
      throw new Error("Camera access is turned off. Enable it in Settings to take photos.");
    }
  }
  const options: ImagePicker.ImagePickerOptions = { mediaTypes: ["images"], quality: 1 };
  const result =
    source === "camera"
      ? await ImagePicker.launchCameraAsync(options)
      : await ImagePicker.launchImageLibraryAsync(options);
  const asset = result.canceled ? null : result.assets[0];
  return asset ? compressImage(asset) : null;
}

export async function pickPdf(maxBytes: number): Promise<PickedFile | null> {
  const result = await DocumentPicker.getDocumentAsync({
    type: "application/pdf",
    copyToCacheDirectory: true,
  });
  const asset = result.canceled ? null : result.assets[0];
  if (!asset) return null;
  if (asset.size !== undefined && asset.size > maxBytes) {
    throw new Error(`That PDF is too large (maximum ${Math.round(maxBytes / (1024 * 1024))} MB).`);
  }
  return { uri: asset.uri, name: asset.name || "document.pdf", type: "application/pdf" };
}

export function uploadDocument(
  applicationId: string,
  documentType: string,
  file: PickedFile,
): Promise<DocumentOut> {
  const form = new FormData();
  form.append("application_id", applicationId);
  form.append("document_type", documentType);
  // Expo's fetch needs a real Blob: expo-file-system's File implements Blob (the old React Native
  // {uri, name, type} descriptor is rejected as an "Unsupported FormDataPart"). Its MIME type comes
  // from the file extension, which compressImage()/pickPdf() always set (.jpg / .pdf).
  form.append("file", new File(file.uri), file.name);
  return api<DocumentOut>("/documents", { method: "POST", body: form });
}
