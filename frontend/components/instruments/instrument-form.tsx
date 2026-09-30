"use client";

import { useEffect, useMemo, useState, type FormEvent } from "react";

import { FormField } from "@/components/auth/form-field";
import { SelectField } from "@/components/select-field";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { CategoryPicker } from "@/components/instruments/category-picker";
import {
  DynamicFieldRenderer,
  initCategoryValues,
  validateCategoryValues,
} from "@/components/instruments/dynamic-field-renderer";
import { ApiError, api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { categoryById, getInstrumentMeta } from "@/lib/meta";
import type { Instrument, InstrumentMeta } from "@/lib/types";

type Values = {
  instrument_type: string;
  manufacturer: string;
  model: string;
  serial_number: string;
  capacity: string;
  capacity_unit: string;
  accuracy_class: string;
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
    address: i.address,
    state_code: i.state_code,
    district_code: i.district_code,
    latitude: i.latitude?.toString() ?? "",
    longitude: i.longitude?.toString() ?? "",
  };
}

// Decimals go over the wire as strings so the backend's Decimal parsing is exact.
function payload(v: Values): Record<string, string | null> {
  const nullable = (s: string) => (s.trim() === "" ? null : s.trim());
  return {
    instrument_type: v.instrument_type,
    manufacturer: v.manufacturer,
    model: v.model,
    serial_number: v.serial_number,
    capacity: v.capacity.trim(),
    capacity_unit: v.capacity_unit,
    accuracy_class: nullable(v.accuracy_class),
    address: v.address,
    state_code: v.state_code,
    district_code: v.district_code,
    latitude: nullable(v.latitude),
    longitude: nullable(v.longitude),
  };
}

type Props =
  | { mode: "create"; initial?: undefined; onSaved: (i: Instrument) => void }
  | { mode: "edit"; initial: Instrument; onSaved: (i: Instrument) => void };

export function InstrumentForm({ mode, initial, onSaved }: Props) {
  const { user } = useAuth();
  const [meta, setMeta] = useState<InstrumentMeta | null>(null);
  const [metaError, setMetaError] = useState(false);
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

  // Spec 16: the optional richer category system, additive alongside the flat fields above.
  // category_id/category_values are a paired nullable field on the backend — both null (no
  // category assigned) or both set. Kept as separate state from `Values` because their shape
  // (a number id + an arbitrary, category-schema-shaped JSON object) doesn't fit the flat
  // string-keyed payload() below.
  const [categoryId, setCategoryId] = useState<number | null>(initial?.category_id ?? null);
  const [categoryValues, setCategoryValues] = useState<Record<string, unknown>>(
    initial?.category_values ?? {},
  );
  const [categoryFieldErrors, setCategoryFieldErrors] = useState<Record<string, string>>({});

  useEffect(() => {
    getInstrumentMeta().then(setMeta, () => setMetaError(true));
  }, []);

  const selectedCategory = useMemo(() => categoryById(meta, categoryId), [meta, categoryId]);

  // Changing the category swaps in a fresh values object for the new schema — a newly-selected
  // category has no prior values to preserve, but re-selecting the same one (e.g. after the
  // search box re-renders the list) is a no-op that keeps whatever the user already filled in.
  function handleCategoryChange(nextId: number | null) {
    if (nextId === categoryId) return;
    setCategoryId(nextId);
    setCategoryFieldErrors({});
    setCategoryValues(nextId === null ? {} : initCategoryValues(categoryById(meta, nextId)?.field_schema ?? []));
  }

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
        if (!allowed.includes(next.capacity_unit)) next.capacity_unit = "";
      }
      if (key === "state_code") {
        const allowed = meta?.regions.find((r) => r.state_code === value)?.districts ?? [];
        if (!allowed.some((d) => d.code === next.district_code)) next.district_code = "";
      }
      return next;
    });
  }

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setFieldErrors({});

    // Top-level required-field presence only — mirrors the backend's own validation scope
    // exactly (spec 16 §7); see dynamic-field-renderer.tsx's validateCategoryValues for why.
    const categoryErrs =
      categoryId !== null ? validateCategoryValues(selectedCategory?.field_schema ?? [], categoryValues) : {};
    setCategoryFieldErrors(categoryErrs);
    if (Object.keys(categoryErrs).length > 0) {
      setError("Please fix the highlighted fields.");
      return;
    }

    const body = payload(values);
    let request: Record<string, unknown>;
    if (mode === "edit") {
      // PATCH only what changed; instrument_type is not editable.
      const before = payload(toValues(initial));
      request = Object.fromEntries(
        Object.entries(body).filter(([k, v]) => k !== "instrument_type" && v !== before[k]),
      );
      // category_id/category_values must be PATCHed together (never one without the other) —
      // only include the pair at all if it actually changed from the instrument's current one.
      const initialCategoryId = initial.category_id;
      const initialCategoryValues = initial.category_values ?? {};
      const categoryPairChanged =
        categoryId !== initialCategoryId ||
        (categoryId !== null && JSON.stringify(categoryValues) !== JSON.stringify(initialCategoryValues));
      if (categoryPairChanged) {
        request.category_id = categoryId;
        request.category_values = categoryId === null ? null : categoryValues;
      }
      if (Object.keys(request).length === 0) {
        onSaved(initial);
        return;
      }
    } else {
      request = Object.fromEntries(Object.entries(body).filter(([, v]) => v !== null));
      // Both existing instrument_type-only creation and category-driven creation stay possible:
      // category_id/category_values are only sent at all when a category was actually chosen.
      if (categoryId !== null) {
        request.category_id = categoryId;
        request.category_values = categoryValues;
      }
    }

    setSubmitting(true);
    try {
      const saved = await api<Instrument>(
        mode === "edit" ? `/instruments/${initial.id}` : "/instruments",
        { method: mode === "edit" ? "PATCH" : "POST", body: JSON.stringify(request) },
      );
      onSaved(saved);
    } catch (err) {
      if (err instanceof ApiError) {
        const { body: formLevel, ...fields } = err.fieldErrors;
        setError(formLevel ?? err.message);
        setFieldErrors(fields);
      } else {
        setError("Could not reach the server.");
      }
      setSubmitting(false);
    }
  }

  // Never re-derive the lock rule client-side: disable exactly what the backend reports.
  const locked = new Set(mode === "edit" ? initial.locked_fields : []);
  const locationLocked = locked.has("address") || locked.has("latitude") || locked.has("longitude");
  const categoryLocked = locked.has("category_id") || locked.has("category_values");

  if (metaError) {
    return (
      <Alert variant="destructive">
        <AlertDescription>Could not load the form. Please reload the page.</AlertDescription>
      </Alert>
    );
  }
  if (!meta) return <p className="text-sm text-muted-foreground">Loading form…</p>;

  const typeOptions = meta.types.map((t) => ({ value: t.value, label: t.label }));
  const unitOptions = units.map((u) => ({ value: u, label: u }));
  const classOptions = [
    { value: NO_CLASS, label: "Not specified" },
    ...meta.accuracy_classes.map((c) => ({ value: c, label: `Class ${c}` })),
  ];
  const stateOptions = meta.regions.map((r) => ({ value: r.state_code, label: r.state_name }));
  const districtOptions = districts.map((d) => ({ value: d.code, label: d.name }));

  return (
    <form onSubmit={onSubmit} className="grid max-w-2xl gap-6" noValidate>
      {error ? (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      ) : null}

      {locked.size > 0 ? (
        <Alert>
          <AlertDescription>
            {locationLocked
              ? "An inspection is scheduled for this instrument; its address and coordinates can't be changed until the application is completed or rejected."
              : "This instrument has an application in progress; these details can't be changed."}
          </AlertDescription>
        </Alert>
      ) : null}

      <fieldset className="grid gap-4 sm:grid-cols-2">
        <legend className="mb-2 text-sm font-medium">Instrument</legend>
        <SelectField
          name="instrument_type"
          label="Type"
          value={values.instrument_type}
          options={typeOptions}
          onChange={(v) => set("instrument_type", v)}
          disabled={mode === "edit"}
          error={fieldErrors.instrument_type}
        />
        <FormField
          name="manufacturer"
          label="Manufacturer"
          value={values.manufacturer}
          onChange={(e) => set("manufacturer", e.target.value)}
          required
          disabled={locked.has("manufacturer")}
          error={fieldErrors.manufacturer}
        />
        <FormField
          name="model"
          label="Model"
          value={values.model}
          onChange={(e) => set("model", e.target.value)}
          required
          disabled={locked.has("model")}
          error={fieldErrors.model}
        />
        <FormField
          name="serial_number"
          label="Serial number"
          value={values.serial_number}
          onChange={(e) => set("serial_number", e.target.value.toUpperCase())}
          autoCapitalize="characters"
          hint="Letters, digits and - / . _ only."
          required
          disabled={locked.has("serial_number")}
          error={fieldErrors.serial_number}
        />
        <FormField
          name="capacity"
          label="Maximum capacity"
          value={values.capacity}
          onChange={(e) => set("capacity", e.target.value)}
          inputMode="decimal"
          required
          disabled={locked.has("capacity")}
          error={fieldErrors.capacity}
        />
        <SelectField
          name="capacity_unit"
          label="Unit"
          value={values.capacity_unit}
          options={unitOptions}
          onChange={(v) => set("capacity_unit", v)}
          placeholder={values.instrument_type ? "Select…" : "Choose a type first"}
          disabled={!values.instrument_type || locked.has("capacity_unit")}
          error={fieldErrors.capacity_unit}
        />
        <SelectField
          name="accuracy_class"
          label="Accuracy class (optional)"
          value={values.accuracy_class || NO_CLASS}
          options={classOptions}
          onChange={(v) => set("accuracy_class", v === NO_CLASS ? "" : v)}
          disabled={locked.has("accuracy_class")}
          error={fieldErrors.accuracy_class}
        />
      </fieldset>

      <fieldset className="grid gap-4">
        <legend className="mb-2 text-sm font-medium">Category (optional)</legend>
        <p className="text-sm text-muted-foreground">
          Pick one of the 33 instrument categories to capture its category-specific fields
          alongside the details above. Leaving this unset still lets you register the instrument
          with just the flat fields.
        </p>
        <CategoryPicker
          categories={meta.categories}
          value={categoryId}
          onChange={handleCategoryChange}
          disabled={categoryLocked}
          error={fieldErrors.category_id}
        />
        {fieldErrors.category_values ? (
          <Alert variant="destructive">
            <AlertDescription>{fieldErrors.category_values}</AlertDescription>
          </Alert>
        ) : null}
        {selectedCategory ? (
          <DynamicFieldRenderer
            fields={selectedCategory.field_schema}
            values={categoryValues}
            onChange={(key, value) => setCategoryValues((prev) => ({ ...prev, [key]: value }))}
            errors={categoryFieldErrors}
            disabled={categoryLocked}
            className="rounded-lg border p-4"
          />
        ) : null}
      </fieldset>

      <fieldset className="grid gap-4 sm:grid-cols-2">
        <legend className="mb-2 text-sm font-medium">Location</legend>
        <div className="sm:col-span-2">
          <FormField
            name="address"
            label="Address where it is installed"
            value={values.address}
            onChange={(e) => set("address", e.target.value)}
            required
            disabled={locked.has("address")}
            error={fieldErrors.address}
          />
        </div>
        <SelectField
          name="state_code"
          label="State"
          value={values.state_code}
          options={stateOptions}
          onChange={(v) => set("state_code", v)}
          disabled={locked.has("state_code")}
          error={fieldErrors.state_code}
        />
        <SelectField
          name="district_code"
          label="District"
          value={values.district_code}
          options={districtOptions}
          onChange={(v) => set("district_code", v)}
          disabled={!values.state_code || locked.has("district_code")}
          error={fieldErrors.district_code}
        />
        <FormField
          name="latitude"
          label="Latitude (optional)"
          value={values.latitude}
          onChange={(e) => set("latitude", e.target.value)}
          inputMode="decimal"
          placeholder="23.7957"
          disabled={locked.has("latitude")}
          error={fieldErrors.latitude}
        />
        <FormField
          name="longitude"
          label="Longitude (optional)"
          value={values.longitude}
          onChange={(e) => set("longitude", e.target.value)}
          inputMode="decimal"
          placeholder="86.4304"
          disabled={locked.has("longitude")}
          error={fieldErrors.longitude}
        />
      </fieldset>

      <div>
        <Button type="submit" className="h-10" disabled={submitting}>
          {submitting ? "Saving…" : mode === "edit" ? "Save changes" : "Register instrument"}
        </Button>
      </div>
    </form>
  );
}
