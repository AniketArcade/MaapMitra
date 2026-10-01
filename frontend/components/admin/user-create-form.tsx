"use client";

import { useEffect, useState, type FormEvent } from "react";

import { FormField } from "@/components/auth/form-field";
import { SelectField } from "@/components/select-field";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { ApiError, createUser } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { getInstrumentMeta } from "@/lib/meta";
import type { CreateUserRequest, InstrumentMeta } from "@/lib/types";

const ROLE_OPTIONS = [
  { value: "LM_OFFICER", label: "LM Officer" },
  { value: "DISTRICT_ADMIN", label: "District Admin" },
  { value: "STATE_ADMIN", label: "State Admin" },
];

// Spec 18 §4/D3: a STATE_ADMIN creator may only create these two roles, and only in their own
// state — POST /api/users rejects (422) a role or state_code outside this, so the form locks
// both rather than letting the server reject a value the UI itself offered.
const STATE_ADMIN_ROLE_OPTIONS = ROLE_OPTIONS.filter((o) => o.value !== "STATE_ADMIN");

function validate(body: CreateUserRequest): Record<string, string> {
  const errors: Record<string, string> = {};
  if (!body.full_name) errors.full_name = "Enter a name.";
  if (!body.email.includes("@")) errors.email = "Enter a valid email.";
  if (body.password.length < 8) errors.password = "At least 8 characters.";
  if (!body.state_code) errors.state_code = "Select a state.";
  if (body.role !== "STATE_ADMIN" && !body.district_code) {
    errors.district_code = "Select a district.";
  }
  return errors;
}

// Spec 17 §6.6: modeled directly on components/auth/register-form.tsx's structure (FormField +
// SelectField, client validate() merged with server ApiError.fieldErrors on 422), restricted to
// the three roles POST /api/users already accepts (STATE_ADMIN/DISTRICT_ADMIN/LM_OFFICER — GATC
// is provisioned outside this form, spec 17 D2).
export function UserCreateForm({ onCreated }: { onCreated: () => void }) {
  const { user: creator } = useAuth();
  const isStateAdminCreator = creator?.role === "STATE_ADMIN";
  const [regions, setRegions] = useState<InstrumentMeta["regions"] | null>(null);
  const [role, setRole] = useState("LM_OFFICER");
  const [stateCode, setStateCode] = useState(
    isStateAdminCreator ? (creator?.state_code ?? "") : "",
  );
  const [districtCode, setDistrictCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    getInstrumentMeta().then((m) => setRegions(m.regions), () => undefined);
  }, []);

  const districtsForState = regions?.find((r) => r.state_code === stateCode)?.districts ?? [];

  function handleRoleChange(value: string) {
    setRole(value);
    if (value === "STATE_ADMIN") setDistrictCode("");
  }

  function handleStateChange(value: string) {
    setStateCode(value);
    setDistrictCode("");
  }

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const body: CreateUserRequest = {
      email: String(form.get("email") ?? "").trim(),
      full_name: String(form.get("full_name") ?? "").trim(),
      phone: String(form.get("phone") ?? "").trim() || undefined,
      role: role as CreateUserRequest["role"],
      password: String(form.get("password") ?? ""),
      state_code: stateCode,
      district_code: role === "STATE_ADMIN" ? undefined : districtCode,
    };
    const clientErrors = validate(body);
    setFieldErrors(clientErrors);
    setError(null);
    if (Object.keys(clientErrors).length) return;

    setSubmitting(true);
    try {
      await createUser(body);
      onCreated();
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message);
        setFieldErrors(err.fieldErrors);
      } else {
        setError("Could not reach the server.");
      }
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={onSubmit} className="grid gap-4" noValidate>
      {error ? (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      ) : null}
      <FormField name="full_name" label="Full name" required error={fieldErrors.full_name} />
      <FormField name="email" label="Email" type="email" required error={fieldErrors.email} />
      <FormField name="phone" label="Phone (optional)" type="tel" error={fieldErrors.phone} />
      <FormField
        name="password"
        label="Initial password"
        type="password"
        required
        hint="At least 8 characters."
        error={fieldErrors.password}
      />
      <SelectField
        name="role"
        label="Role"
        value={role}
        options={isStateAdminCreator ? STATE_ADMIN_ROLE_OPTIONS : ROLE_OPTIONS}
        onChange={handleRoleChange}
        error={fieldErrors.role}
      />
      <div className="grid grid-cols-2 gap-3">
        <SelectField
          name="state_code"
          label="State"
          value={stateCode}
          options={(regions ?? []).map((r) => ({ value: r.state_code, label: r.state_name }))}
          onChange={handleStateChange}
          placeholder={regions ? "Select…" : "Loading…"}
          disabled={isStateAdminCreator || !regions}
          error={fieldErrors.state_code}
        />
        <SelectField
          name="district_code"
          label="District"
          value={districtCode}
          options={districtsForState.map((d) => ({ value: d.code, label: d.name }))}
          onChange={setDistrictCode}
          placeholder={
            role === "STATE_ADMIN" ? "Not applicable" : stateCode ? "Select…" : "Choose a state first"
          }
          disabled={role === "STATE_ADMIN" || !stateCode}
          error={fieldErrors.district_code}
        />
      </div>
      <Button type="submit" className="h-10" disabled={submitting}>
        {submitting ? "Creating…" : "Create account"}
      </Button>
    </form>
  );
}
