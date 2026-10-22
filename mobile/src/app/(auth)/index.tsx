import { Link, router } from "expo-router";
import { useState } from "react";

import { Button, ErrorText, InfoText, Screen, TextField, Title } from "@/components/ui";
import { ApiError, describeError } from "@/lib/api";
import { useAuth } from "@/lib/auth";

export default function Login() {
  const { login, notice, clearNotice } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);

  async function submit() {
    setBusy(true);
    setError(null);
    setFieldErrors({});
    clearNotice();
    try {
      await login(email.trim(), password);
      // Navigation happens automatically: the root layout's Protected guards switch on the role.
    } catch (err) {
      if (err instanceof ApiError && err.status === 422) setFieldErrors(err.fieldErrors);
      setError(describeError(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Screen>
      <Title>Sign in</Title>
      {notice ? <InfoText>{notice}</InfoText> : null}
      {error ? <ErrorText>{error}</ErrorText> : null}
      <TextField
        label="Email"
        value={email}
        onChangeText={setEmail}
        autoCapitalize="none"
        autoComplete="email"
        keyboardType="email-address"
        error={fieldErrors.email}
      />
      <TextField
        label="Password"
        value={password}
        onChangeText={setPassword}
        secureTextEntry
        autoCapitalize="none"
        autoComplete="current-password"
        error={fieldErrors.password}
        onSubmitEditing={() => void submit()}
      />
      <Button label="Sign in" onPress={() => void submit()} loading={busy} disabled={!email || !password} />
      <Button label="Create a business account" variant="secondary" onPress={() => router.push("/register")} />
      <Link href="/verify" style={{ textAlign: "center", color: "#1d4ed8", paddingVertical: 8 }}>
        Verify a certificate
      </Link>
    </Screen>
  );
}
