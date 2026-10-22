import type { Certificate } from "@api-types";
import { router } from "expo-router";
import { useState } from "react";
import { Image, StyleSheet, Text, View } from "react-native";

import { Button, ErrorText, InfoText, Muted, Title } from "@/components/ui";
import { describeError } from "@/lib/api";
import { openCertificatePdf, shareCertificatePdf } from "@/lib/certificates";
import { colors } from "@/lib/theme";
import { formatDate } from "@/lib/verify";

function Row({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.row}>
      <Text style={styles.label}>{label}</Text>
      <Text style={styles.value}>{value}</Text>
    </View>
  );
}

/** Certificate detail body, shared by every role that may open a certificate. */
export function CertificateView({ certificate: c }: { certificate: Certificate }) {
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<"view" | "share" | null>(null);

  async function run(kind: "view" | "share", action: () => Promise<void>) {
    setBusy(kind);
    setError(null);
    try {
      await action();
    } catch (err) {
      setError(
        err instanceof Error && !("status" in err) ? "Couldn't open the certificate file. Try again." : describeError(err),
      );
    } finally {
      setBusy(null);
    }
  }

  return (
    <View style={{ gap: 12 }}>
      <Muted>{c.certificate_number}</Muted>
      <Title>Certificate of Verification</Title>
      <Muted>
        {c.manufacturer} {c.model} · S/N {c.serial_number} · {c.organization_name}
      </Muted>

      {error ? <ErrorText>{error}</ErrorText> : null}
      {c.is_expiring_soon ? <InfoText>Expiring soon: a re-verification may be needed shortly.</InfoText> : null}
      {c.superseded_by_certificate_id ? (
        <View style={{ gap: 6 }}>
          <Muted>This certificate has been superseded.</Muted>
          <Button
            label="View the current certificate"
            variant="secondary"
            onPress={() => router.push({ pathname: "/certificates/[id]", params: { id: c.superseded_by_certificate_id! } })}
          />
        </View>
      ) : null}

      <View style={styles.card}>
        <Image
          source={{ uri: c.qr_code_data_uri }}
          accessibilityLabel="QR code linking to the public verification page"
          style={styles.qr}
          resizeMode="contain"
        />
        <Row label="Instrument" value={c.instrument_uid} />
        <Row label="Capacity" value={`${c.capacity} ${c.capacity_unit}`} />
        <Row label="Status" value={c.status} />
        <Row label="Valid from" value={formatDate(c.valid_from)} />
        <Row label="Valid until" value={formatDate(c.valid_until)} />
      </View>

      {c.supersedes_certificate_id ? (
        <Button
          label="View the certificate this replaces"
          variant="secondary"
          onPress={() => router.push({ pathname: "/certificates/[id]", params: { id: c.supersedes_certificate_id! } })}
        />
      ) : null}

      <Button label="View PDF" onPress={() => void run("view", () => openCertificatePdf(c.id))} loading={busy === "view"} />
      <Button
        label="Share / save PDF"
        variant="secondary"
        onPress={() => void run("share", () => shareCertificatePdf(c.id, c.certificate_number))}
        loading={busy === "share"}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  card: { backgroundColor: colors.card, borderRadius: 12, padding: 14, gap: 10, borderWidth: 1, borderColor: colors.border },
  qr: { width: 160, height: 160, alignSelf: "center", backgroundColor: "#fff" },
  row: { flexDirection: "row", justifyContent: "space-between", gap: 12 },
  label: { color: colors.muted, fontSize: 14 },
  value: { color: colors.text, fontSize: 14, flexShrink: 1, textAlign: "right" },
});
