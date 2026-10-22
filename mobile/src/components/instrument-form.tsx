import type { Instrument, InstrumentMeta } from "@api-types";
import { useEffect, useMemo, useState } from "react";
import { Switch, Text, View } from "react-native";

import { Button, ErrorText, InfoText, Loading, Muted, Select, TextField } from "@/components/ui";
import { ApiError, api, describeError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { getInstrumentMeta } from "@/lib/meta";

type Values = {
  instrument_type: string;
  manufacturer: string;
  model: string;
  serial_number: string;
  capacity: string;
  capacity_unit: string;
  accuracy_class: string;
  transportable: boolean;
  address: string;
  state_code: string;
  district_code: string;
  latitude: string;
  longitude: string;
};

const NO_CLASS = "__none__";

function toValues(i: Instrument): Values {
  return {
    instrument_type: i.instrument_type,
    manufacturer: i.manufacturer,
    model: i.model,
    serial_number: i.serial_number,
    capacity: String(i.capacity),
    capacity_unit: i.capacity_unit,
    accuracy_class: i.accuracy_class ?? "",
    transportable: i.transportable,
    address: i.address,
    state_code: i.state_code,
    district_code: i.district_code,
    latitude: i.latitude?.toString() ?? "",
    longitude: i.longitude?.toString() ?? "",
  };
}

// Decimals go over the wire as strings so the backend's Decimal parsing is exact.
function payload(v: Values): Record<string, string | boolean | null> {
  const nullable = (s: string) => (s.trim() === "" ? null : s.trim());
  return {
    instrument_type: v.instrument_type,
    manufacturer: v.manufacturer.trim(),
    model: v.model.trim(),
    serial_number: v.serial_number.trim(),
    capacity: v.capacity.trim(),
    capacity_unit: v.capacity_unit,
    accuracy_class: nullable(v.accuracy_class),
    transportable: v.transportable,
    address: v.address.trim(),
    state_code: v.state_code,
    district_code: v.district_code,
    latitude: nullable(v.latitude),
    longitude: nullable(v.longitude),
  };
}

type Props =
  | { mode: "create"; initial?: undefined; onSaved: (i: Instrument) => void }
  | { mode: "edit"; initial: Instrument; onSaved: (i: Instrument) => void };

// Instrument categories (spec 16, optional on the backend) are not editable in the app yet:
// create sends only the flat fields, and edit never touches category_id/category_values.
export function InstrumentForm({ mode, initial, onSaved }: Props) {
  const { user } = useAuth();
  const [meta, setMeta] = useState<InstrumentMeta | null>(null);
  const [metaError, setMetaError] = useState<string | null>(null);
  const [values, setValues] = useState<Values>(() =>
    initial
      ? toValues(initial)
      : {
          instrument_type: "",
          manufacturer: "",
          model: "",
          serial_number: "",
          capacity: "",
          capacity_unit: "",
          accuracy_class: "",
          transportable: true,
          address: "",
          state_code: user?.state_code ?? "",
          district_code: user?.district_code ?? "",
          latitude: "",
          longitude: "",
        },
  );
  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    getInstrumentMeta().then(setMeta, (err: unknown) => setMetaError(describeError(err)));
  }, []);

  const units = useMemo(
    () => meta?.types.find((t) => t.value === values.instrument_type)?.units ?? [],
    [meta, values.instrument_type],
  );
  const districts = useMemo(
    () => meta?.regions.find((r) => r.state_code === values.state_code)?.districts ?? [],
    [meta, values.state_code],
  );

  function set<K extends keyof Values>(key: K, value: Values[K]) {
    setValues((prev) => {
      const next = { ...prev, [key]: value };
      // Keep dependent dropdowns consistent.
      if (key === "instrument_type") {
        const allowed = meta?.types.find((t) => t.value === value)?.units ?? [];
        if (!(allowed as readonly string[]).includes(next.capacity_unit)) next.capacity_unit = "";
      }
      if (key === "state_code") {
        const allowed = meta?.regions.find((r) => r.state_code === value)?.districts ?? [];
        if (!allowed.some((d) => d.code === next.district_code)) next.district_code = "";
      }
      return next;
    });
  }

  async function submit() {
    setError(null);
    setFieldErrors({});
    const body = payload(values);
    let request: Record<string, unknown>;
    if (mode === "edit") {
      // PATCH only what changed; the instrument type is not editable.
      const before = payload(toValues(initial));
      request = Object.fromEntries(
        Object.entries(body).filter(([k, v]) => k !== "instrument_type" && v !== before[k]),
      );
      if (Object.keys(request).length === 0) {
        onSaved(initial);
        return;
      }
    } else {
      request = Object.fromEntries(Object.entries(body).filter(([, v]) => v !== null));
    }

    setSubmitting(true);
    try {
      const saved = await api<Instrument>(
        mode === "edit" ? `/instruments/${initial.id}` : "/instruments",
        { method: mode === "edit" ? "PATCH" : "POST", body: JSON.stringify(request) },
      );
      onSaved(saved);
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

  // Never re-derive the lock rule client-side: disable exactly what the backend reports.
  const locked = new Set(mode === "edit" ? initial.locked_fields : []);
  const locationLocked = locked.has("address") || locked.has("latitude") || locked.has("longitude");

  if (metaError) return <ErrorText>{metaError}</ErrorText>;
  if (!meta) return <Loading label="Loading form…" />;

  const typeOptions = meta.types.map((t) => ({ value: t.value, label: t.label }));
  const unitOptions = units.map((u) => ({ value: u, label: u }));
  const classOptions = [
    { value: NO_CLASS, label: "Not specified" },
    ...meta.accuracy_classes.map((c) => ({ value: c, label: `Class ${c}` })),
  ];
  const stateOptions = meta.regions.map((r) => ({ value: r.state_code, label: r.state_name }));
  const districtOptions = districts.map((d) => ({ value: d.code, label: d.name }));
  const canSubmit =
    values.instrument_type &&
    values.manufacturer.trim() &&
    values.model.trim() &&
    values.serial_number.trim() &&
    values.capacity.trim() &&
    values.capacity_unit &&
    values.address.trim() &&
    values.state_code &&
    values.district_code;

  return (
    <View style={{ gap: 12 }}>
      {error ? <ErrorText>{error}</ErrorText> : null}
      {locked.size > 0 ? (
        <InfoText>
          {locationLocked
            ? "An inspection is scheduled for this instrument; its address and coordinates can't be changed until the application is completed or rejected."
            : "This instrument has an application in progress; these details can't be changed."}
        </InfoText>
      ) : null}
      {mode === "edit" && initial.category_id !== null ? (
        <Muted>Category details can be edited on the website.</Muted>
      ) : null}

      <Select
        label="Type"
        value={values.instrument_type}
        options={typeOptions}
        onChange={(v) => set("instrument_type", v)}
        disabled={mode === "edit"}
        error={fieldErrors.instrument_type}
      />
      <TextField
        label="Manufacturer"
        value={values.manufacturer}
        onChangeText={(v) => set("manufacturer", v)}
        editable={!locked.has("manufacturer")}
        error={fieldErrors.manufacturer}
      />
      <TextField
        label="Model"
        value={values.model}
        onChangeText={(v) => set("model", v)}
        editable={!locked.has("model")}
        error={fieldErrors.model}
      />
      <TextField
        label="Serial number"
        value={values.serial_number}
        onChangeText={(v) => set("serial_number", v.toUpperCase())}
        autoCapitalize="characters"
        autoCorrect={false}
        editable={!locked.has("serial_number")}
        error={fieldErrors.serial_number}
      />
      <TextField
        label="Maximum capacity"
        value={values.capacity}
        onChangeText={(v) => set("capacity", v)}
        keyboardType="decimal-pad"
        editable={!locked.has("capacity")}
        error={fieldErrors.capacity}
      />
      <Select
        label="Unit"
        value={values.capacity_unit}
        options={unitOptions}
        onChange={(v) => set("capacity_unit", v)}
        placeholder={values.instrument_type ? "Select…" : "Choose a type first"}
        disabled={!values.instrument_type || locked.has("capacity_unit")}
        error={fieldErrors.capacity_unit}
      />
      <Select
        label="Accuracy class (optional)"
        value={values.accuracy_class || NO_CLASS}
        options={classOptions}
        onChange={(v) => set("accuracy_class", v === NO_CLASS ? "" : v)}
        disabled={locked.has("accuracy_class")}
        error={fieldErrors.accuracy_class}
      />
      <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: 12 }}>
        <View style={{ flex: 1 }}>
          <Text style={{ fontWeight: "600" }}>Can the instrument be transported?</Text>
          <Muted>Yes: verified at an office/test centre. No: verified on-site where it stands.</Muted>
        </View>
        <Switch
          value={values.transportable}
          disabled={locked.has("transportable")}
          onValueChange={(v) => set("transportable", v)}
        />
      </View>
      {fieldErrors.transportable ? <Text style={{ color: "#b91c1c" }}>{fieldErrors.transportable}</Text> : null}

      <TextField
        label="Address where it is installed"
        value={values.address}
        onChangeText={(v) => set("address", v)}
        editable={!locked.has("address")}
        error={fieldErrors.address}
      />
      <Select
        label="State"
        value={values.state_code}
        options={stateOptions}
        onChange={(v) => set("state_code", v)}
        disabled={locked.has("state_code")}
        error={fieldErrors.state_code}
      />
      <Select
        label="District"
        value={values.district_code}
        options={districtOptions}
        onChange={(v) => set("district_code", v)}
        disabled={!values.state_code || locked.has("district_code")}
        error={fieldErrors.district_code}
      />
      <TextField
        label="Latitude (optional)"
        value={values.latitude}
        onChangeText={(v) => set("latitude", v)}
        keyboardType="numbers-and-punctuation"
        placeholder="23.7957"
        editable={!locked.has("latitude")}
        error={fieldErrors.latitude}
      />
      <TextField
        label="Longitude (optional)"
        value={values.longitude}
        onChangeText={(v) => set("longitude", v)}
        keyboardType="numbers-and-punctuation"
        placeholder="86.4304"
        editable={!locked.has("longitude")}
        error={fieldErrors.longitude}
      />

      <Button
        label={mode === "edit" ? "Save changes" : "Register instrument"}
        onPress={() => void submit()}
        loading={submitting}
        disabled={!canSubmit}
      />
    </View>
  );
}
