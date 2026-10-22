import { DateTimePickerAndroid } from "@react-native-community/datetimepicker";
import type { ApplicationDetail, GatcEligibleOrg, GatcOrgUser, Instrument } from "@api-types";
import { useEffect, useState } from "react";
import { Modal, Platform, ScrollView, StyleSheet, Text, View } from "react-native";

import { Button, ErrorText, Muted, Select } from "@/components/ui";
import { api } from "@/lib/api";
import { addDaysToIsoDate, isoToPickerDate, pickerDateToIso, todayInTimezone } from "@/lib/scheduling";
import { colors } from "@/lib/theme";
import { formatDate } from "@/lib/verify";

type Mode = "self" | "gatc";

/**
 * Schedules an inspection (optionally routing it to a GATC test centre) or, with `reschedule`,
 * only changes its date. Dates are validated against the backend's timezone window; the server is
 * still the authority.
 */
export function ScheduleDialog({
  visible,
  app,
  timezone,
  maxDaysAhead,
  reschedule = false,
  busy,
  error,
  onConfirm,
  onClose,
}: {
  visible: boolean;
  app: ApplicationDetail;
  timezone: string;
  maxDaysAhead: number;
  reschedule?: boolean;
  busy: boolean;
  error: string | null;
  onConfirm: (body: { scheduled_date: string; gatc_organization_id?: string; gatc_user_id?: string }) => void;
  onClose: () => void;
}) {
  const today = todayInTimezone(timezone);
  const max = addDaysToIsoDate(today, maxDaysAhead);
  const [date, setDate] = useState(reschedule && app.inspection ? app.inspection.scheduled_date : today);
  const [mode, setMode] = useState<Mode>("self");
  const [eligible, setEligible] = useState<GatcEligibleOrg[] | null>(null);
  const [orgId, setOrgId] = useState("");
  const [users, setUsers] = useState<GatcOrgUser[] | null>(null);
  const [userId, setUserId] = useState("");

  // GATC routing is only offered for an OFFICE_TEST_CENTRE application whose instrument has a
  // category; anything else stays self-assign-only (fails closed: self-assign always works).
  useEffect(() => {
    if (!visible || reschedule || app.verification_mode !== "OFFICE_TEST_CENTRE") return;
    let cancelled = false;
    api<Instrument>(`/instruments/${app.instrument.id}`)
      .then((i) => (i.category_id === null ? [] : api<GatcEligibleOrg[]>(`/gatc/eligible?category_id=${i.category_id}`)))
      .then((orgs) => !cancelled && setEligible(orgs))
      .catch(() => !cancelled && setEligible([]));
    return () => {
      cancelled = true;
    };
  }, [visible, reschedule, app.verification_mode, app.instrument.id]);

  function chooseOrg(id: string) {
    setOrgId(id);
    setUserId("");
    setUsers(null);
    if (!id) return;
    api<GatcOrgUser[]>(`/gatc/${id}/users`).then(setUsers, () => setUsers([]));
  }

  function pickDate() {
    if (Platform.OS !== "android") return;
    DateTimePickerAndroid.open({
      value: isoToPickerDate(date),
      mode: "date",
      minimumDate: isoToPickerDate(today),
      maximumDate: isoToPickerDate(max),
      onValueChange: (_event, selected) => setDate(pickerDateToIso(selected)),
    });
  }

  const gatcApplicable = !reschedule && app.verification_mode === "OFFICE_TEST_CENTRE";
  const gatcLoading = gatcApplicable && eligible === null;
  const routing = mode === "gatc";
  const canConfirm = !!date && (!routing || (!!orgId && !!userId));

  return (
    <Modal visible={visible} transparent animationType="fade" onRequestClose={onClose}>
      <View style={styles.backdrop}>
        <ScrollView keyboardShouldPersistTaps="handled" contentContainerStyle={{ flexGrow: 1, justifyContent: "flex-end" }}>
          <View style={styles.sheet}>
            <Text style={styles.title}>{reschedule ? "Change the inspection date" : "Schedule the inspection"}</Text>
            {!reschedule ? (
              <Muted>The instrument&apos;s address and coordinates will be locked until the application is completed or rejected.</Muted>
            ) : null}
            {error ? <ErrorText>{error}</ErrorText> : null}

            <Text style={styles.label}>Date</Text>
            <Button label={formatDate(date)} variant="secondary" onPress={pickDate} />
            <Muted>Between {formatDate(today)} and {formatDate(max)}.</Muted>

            {gatcLoading ? <Muted>Checking for eligible GATC test centres…</Muted> : null}
            {eligible && eligible.length > 0 ? (
              <View style={{ gap: 10 }}>
                <Text style={styles.label}>Assign to</Text>
                <View style={{ flexDirection: "row", gap: 8 }}>
                  <View style={{ flex: 1 }}>
                    <Button label="Myself" variant={mode === "self" ? "primary" : "secondary"} onPress={() => setMode("self")} />
                  </View>
                  <View style={{ flex: 1 }}>
                    <Button label="GATC centre" variant={mode === "gatc" ? "primary" : "secondary"} onPress={() => setMode("gatc")} />
                  </View>
                </View>
                {routing ? (
                  <>
                    <Select
                      label="GATC test centre"
                      value={orgId}
                      options={eligible.map((o) => ({ value: o.id, label: `${o.name} (${o.district_code}, ${o.state_code})` }))}
                      onChange={chooseOrg}
                    />
                    {orgId ? (
                      <Select
                        label="Staff member"
                        value={userId}
                        options={(users ?? []).map((u) => ({ value: u.id, label: `${u.full_name} (${u.email})` }))}
                        onChange={setUserId}
                        placeholder={users === null ? "Loading…" : "Select…"}
                      />
                    ) : null}
                  </>
                ) : null}
              </View>
            ) : eligible !== null && !reschedule ? (
              <Muted>No eligible GATC test centre for this instrument: this inspection will be self-assigned.</Muted>
            ) : null}

            <Button
              label={reschedule ? "Save date" : "Schedule"}
              loading={busy}
              disabled={!canConfirm}
              onPress={() =>
                onConfirm({
                  scheduled_date: date,
                  ...(routing && orgId && userId ? { gatc_organization_id: orgId, gatc_user_id: userId } : {}),
                })
              }
            />
            <Button label="Cancel" variant="secondary" onPress={onClose} disabled={busy} />
          </View>
        </ScrollView>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  backdrop: { flex: 1, backgroundColor: "rgba(0,0,0,0.4)" },
  sheet: { backgroundColor: colors.card, borderTopLeftRadius: 16, borderTopRightRadius: 16, padding: 16, gap: 12 },
  title: { fontSize: 20, fontWeight: "700", color: colors.text },
  label: { fontSize: 14, fontWeight: "600", color: colors.text },
});
