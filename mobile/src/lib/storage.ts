import { Platform } from "react-native";
import * as SecureStore from "expo-secure-store";

const REFRESH_KEY = "maapmitra.refresh_token";

// SecureStore has no web implementation; localStorage is only used by the browser preview.
const isWeb = Platform.OS === "web";

export async function getRefreshToken(): Promise<string | null> {
  try {
    if (isWeb) return globalThis.localStorage?.getItem(REFRESH_KEY) ?? null;
    return await SecureStore.getItemAsync(REFRESH_KEY);
  } catch {
    return null;
  }
}

export async function setRefreshToken(token: string): Promise<void> {
  if (isWeb) {
    globalThis.localStorage?.setItem(REFRESH_KEY, token);
    return;
  }
  await SecureStore.setItemAsync(REFRESH_KEY, token);
}

export async function clearRefreshToken(): Promise<void> {
  try {
    if (isWeb) globalThis.localStorage?.removeItem(REFRESH_KEY);
    else await SecureStore.deleteItemAsync(REFRESH_KEY);
  } catch {
    // nothing stored / store unavailable
  }
}
