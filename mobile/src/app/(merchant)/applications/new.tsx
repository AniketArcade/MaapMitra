import type { Application, ApplicationMeta, Instrument, Page } from "@api-types";
import { router, useLocalSearchParams } from "expo-router";
import { useEffect, useState } from "react";

import { Button, ErrorText, Loading, Muted, Screen, Select, TextField } from "@/components/ui";
import { ApiError, api, describeError } from "@/lib/api";
import { getApplicationMeta } from "@/lib/meta";

export default function NewApplication() {
  const { instrument_id } = useLocalSearchParams<{ instrument_id?: string }>();
  const [meta, setMeta] = useState<ApplicationMeta | null>(null);
  const [instruments, setInstruments] = useState<Instrument[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [instrumentId, setInstrumentId] = useState(instrument_id ?? "");
  const [type, setType] = useState("VERIFICATION");
  const [notes, setNotes] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    Promise.all([getApplicationMeta(), api<Page<Instrument>>("/instruments?page_size=100")]).then(
      ([m, page]) => {
        setMeta(m);
        // One active application per instrument: only offer instruments without one.
        setInstruments(page.items.filter((i) => i.active_application === null));
      },
      (err: unknown) => setLoadError(describeError(err)),
    );
  }, []);

  async function submit() {
    setError(null);
    setFieldErrors({});
    if (!instrumentId) {
      setFieldErrors({ instrument_id: "Choose an instrument." });
      return;
    }
    setSubmitting(true);
    try {
      const created = await api<Application>("/applications", {
        method: "POST",
        body: JSON.stringify({
          instrument_id: instrumentId,
          application_type: type,
          ...(notes.trim() ? { business_notes: notes.trim() } : {}),
        }),
      });
      router.replace({ pathname: "/applications/[id]", params: { id: created.id } });
    } catch (err) {
      if (err instanceof ApiError && err.status === 422) {
        const { body: formLevel, ...fields } = err.fieldErrors;
        setError(formLevel ?? err.message);
        setFieldErrors(fields);
      } else {
        setError(describeError(err));
      }
      setSubmitting(false);
    }
  }

  if (loadError) return <Screen hasHeader><ErrorText>{loadError}</ErrorText></Screen>;
  if (!meta || !instruments) return <Loading />;
  if (instruments.length === 0) {
    return (
      <Screen hasHeader>
        <Muted>
          No instrument is available to apply for: every instrument already has an application in progress, or none is
          registered yet.
        </Muted>
        <Button label="Register an instrument" onPress={() => router.replace("/instruments/new")} />
      </Screen>
    );
  }

  return (
    <Screen hasHeader>
      {error ? <ErrorText>{error}</ErrorText> : null}
      <Select
        label="Instrument"
        value={instrumentId}
        options={instruments.map((i) => ({
          value: i.id,
          label: `${i.instrument_uid} · S/N ${i.serial_number} · ${i.capacity} ${i.capacity_unit}`,
        }))}
        onChange={setInstrumentId}
        error={fieldErrors.instrument_id}
      />
      <Select
        label="Application type"
        value={type}
        options={meta.application_types.map((t) => ({ value: t.value, label: t.label }))}
        onChange={setType}
        error={fieldErrors.application_type}
      />
      <TextField
        label="Notes for the officer (optional)"
        value={notes}
        onChangeText={setNotes}
        multiline
        maxLength={1000}
        style={{ minHeight: 96, textAlignVertical: "top", paddingTop: 12 }}
        error={fieldErrors.business_notes}
      />
      <Muted>This creates a draft. You&apos;ll upload the required documents next, then submit.</Muted>
      <Button label="Create draft" onPress={() => void submit()} loading={submitting} />
    </Screen>
  );
}
