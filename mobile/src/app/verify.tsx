import type { VerifyResult } from "@api-types";
import { CameraView, useCameraPermissions } from "expo-camera";
import { useCallback, useRef, useState } from "react";
import { Linking, StyleSheet, View } from "react-native";

import { VerifyResultCard } from "@/components/verify-result";
import { Button, ErrorText, Loading, Muted, Screen, TextField } from "@/components/ui";
import { ApiError } from "@/lib/api";
import { parseCertificateNumber } from "@/lib/qr";
import { getPublicVerify } from "@/lib/verify";

// Public route: no login needed. Shows only what GET /public/verify/{number} returns.
type State =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "not-found" }
  | { kind: "error"; message: string }
  | { kind: "ready"; result: VerifyResult };

export default function Verify() {
  const [permission, requestPermission] = useCameraPermissions();
  const [state, setState] = useState<State>({ kind: "idle" });
  const [manual, setManual] = useState("");
  // The camera fires onBarcodeScanned continuously; lock until the user scans again.
  const locked = useRef(false);

  const check = useCallback(async (raw: string) => {
    const number = parseCertificateNumber(raw);
    if (!number || locked.current) return;
    locked.current = true;
    setState({ kind: "loading" });
    try {
      setState({ kind: "ready", result: await getPublicVerify(number) });
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) setState({ kind: "not-found" });
      else {
        const message =
          err instanceof ApiError && (err.status === 429 || err.status === 0)
            ? err.message
            : "Couldn't check this certificate. Try again.";
        setState({ kind: "error", message });
      }
    }
  }, []);

  function reset() {
    locked.current = false;
    setManual("");
    setState({ kind: "idle" });
  }

  if (state.kind === "loading") return <Loading label="Checking…" />;

  if (state.kind !== "idle") {
    return (
      <Screen>
        {state.kind === "ready" ? <VerifyResultCard result={state.result} /> : null}
        {state.kind === "not-found" ? <ErrorText>Certificate not found.</ErrorText> : null}
        {state.kind === "error" ? <ErrorText>{state.message}</ErrorText> : null}
        <Button label="Verify another" onPress={reset} />
      </Screen>
    );
  }

  return (
    <Screen>
      <Muted>Scan the QR code on a certificate, or type its number.</Muted>
      {permission?.granted ? (
        <View style={styles.cameraBox}>
          <CameraView
            style={StyleSheet.absoluteFill}
            facing="back"
            barcodeScannerSettings={{ barcodeTypes: ["qr"] }}
            onBarcodeScanned={({ data }) => void check(data)}
          />
        </View>
      ) : (
        <View style={{ gap: 8 }}>
          <Muted>
            {permission && !permission.canAskAgain
              ? "Camera access is turned off. Enable it in Settings to scan, or enter the number below."
              : "Allow camera access to scan QR codes, or enter the number below."}
          </Muted>
          {permission && !permission.canAskAgain ? (
            <Button label="Open Settings" variant="secondary" onPress={() => void Linking.openSettings()} />
          ) : (
            <Button label="Allow camera" variant="secondary" onPress={() => void requestPermission()} />
          )}
        </View>
      )}
      <TextField
        label="Certificate number"
        placeholder="LM-CERT-2026-000123"
        value={manual}
        onChangeText={setManual}
        autoCapitalize="characters"
        autoCorrect={false}
        onSubmitEditing={() => void check(manual)}
      />
      <Button label="Verify" onPress={() => void check(manual)} disabled={!manual.trim()} />
    </Screen>
  );
}

const styles = StyleSheet.create({
  cameraBox: { height: 280, borderRadius: 12, overflow: "hidden", backgroundColor: "#000" },
});
