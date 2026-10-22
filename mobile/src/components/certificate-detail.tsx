import type { Certificate } from "@api-types";
import { useLocalSearchParams } from "expo-router";

import { CertificateView } from "@/components/certificate-view";
import { ErrorState, Loading, Screen } from "@/components/ui";
import { api } from "@/lib/api";
import { useAsync } from "@/lib/use-async";

export function CertificateDetail() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const state = useAsync(() => api<Certificate>(`/certificates/${id}`));
  if (!state.data) {
    return state.status === "error" ? (
      <ErrorState message="This certificate wasn't found, or you can't access it." onRetry={state.retry} />
    ) : (
      <Loading />
    );
  }
  return (
    <Screen hasHeader>
      <CertificateView certificate={state.data} />
    </Screen>
  );
}
