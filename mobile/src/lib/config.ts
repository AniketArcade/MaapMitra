const origin = process.env.EXPO_PUBLIC_API_ORIGIN;

if (!origin) {
  throw new Error("EXPO_PUBLIC_API_ORIGIN is not set. Copy .env.example to .env and restart Expo.");
}

/** Backend origin without a trailing slash. Public by nature: no secrets in the app bundle. */
export const API_ORIGIN = origin.replace(/\/+$/, "");
