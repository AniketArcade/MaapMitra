import type { RegionMeta, RegisterRequest } from "@api-types";
import { useEffect, useMemo, useState } from "react";

import { Button, ErrorText, Loading, Screen, Select, TextField, Title } from "@/components/ui";
import { ApiError, describeError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { getPublicRegions } from "@/lib/meta";

type Form = {
  organization_name: string;
  state_code: string;
  district_code: string;
  full_name: string;
  email: string;
  phone: string;
  password: string;
};

const EMPTY: Form = {
  organization_name: "",
  state_code: "",
  district_code: "",
  full_name: "",
  email: "",
  phone: "",
  password: "",
};

export default function Register() {
  const { register } = useAuth();
  const [regions, setRegions] = useState<RegionMeta[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [form, setForm] = useState<Form>(EMPTY);
  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    getPublicRegions().then(setRegions, (err: unknown) => setLoadError(describeError(err)));
  }, []);

  const states = useMemo(
    () => (regions ?? []).map((r) => ({ value: r.state_code, label: r.state_name })),
    [regions],
  );
  const districts = useMemo(
    () =>
      (regions?.find((r) => r.state_code === form.state_code)?.districts ?? []).map((d) => ({
        value: d.code,
        label: d.name,
      })),
    [regions, form.state_code],
  );

  function set<K extends keyof Form>(key: K, value: Form[K]) {
    setForm((prev) => {
      const next = { ...prev, [key]: value };
      if (key === "state_code") next.district_code = ""; // keep the cascade consistent
      return next;
    });
  }

  async function submit() {
    setBusy(true);
    setError(null);
    setFieldErrors({});
    const body: RegisterRequest = {
      organization_name: form.organization_name.trim(),
      state_code: form.state_code,
      district_code: form.district_code,
      full_name: form.full_name.trim(),
      email: form.email.trim(),
      password: form.password,
      ...(form.phone.trim() ? { phone: form.phone.trim() } : {}),
    };
    try {
      await register(body);
    } catch (err) {
      if (err instanceof ApiError && err.status === 422) setFieldErrors(err.fieldErrors);
      setError(describeError(err));
    } finally {
      setBusy(false);
    }
  }

  if (loadError) return <Screen><ErrorText>{loadError}</ErrorText></Screen>;
  if (!regions) return <Loading />;

  return (
    <Screen>
      <Title>Create a business account</Title>
      {error ? <ErrorText>{error}</ErrorText> : null}
      <TextField
        label="Organization name"
        value={form.organization_name}
        onChangeText={(v) => set("organization_name", v)}
        error={fieldErrors.organization_name}
      />
      <Select
        label="State"
        value={form.state_code}
        options={states}
        onChange={(v) => set("state_code", v)}
        error={fieldErrors.state_code}
      />
      <Select
        label="District"
        value={form.district_code}
        options={districts}
        onChange={(v) => set("district_code", v)}
        disabled={!form.state_code}
        error={fieldErrors.district_code}
      />
      <TextField label="Your name" value={form.full_name} onChangeText={(v) => set("full_name", v)} error={fieldErrors.full_name} />
      <TextField
        label="Email"
        value={form.email}
        onChangeText={(v) => set("email", v)}
        autoCapitalize="none"
        keyboardType="email-address"
        error={fieldErrors.email}
      />
      <TextField label="Phone (optional)" value={form.phone} onChangeText={(v) => set("phone", v)} keyboardType="phone-pad" error={fieldErrors.phone} />
      <TextField
        label="Password"
        value={form.password}
        onChangeText={(v) => set("password", v)}
        secureTextEntry
        autoCapitalize="none"
        error={fieldErrors.password}
      />
      <Button
        label="Create account"
        onPress={() => void submit()}
        loading={busy}
        disabled={!form.organization_name || !form.state_code || !form.district_code || !form.full_name || !form.email || !form.password}
      />
    </Screen>
  );
}
