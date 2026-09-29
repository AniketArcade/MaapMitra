// Mirrors backend/app/schemas. Keep in sync.

export type Role =
  | "SUPER_ADMIN"
  | "STATE_ADMIN"
  | "DISTRICT_ADMIN"
  | "LM_OFFICER"
  | "GATC"
  | "BUSINESS";

export const ADMIN_ROLES: readonly Role[] = ["SUPER_ADMIN", "STATE_ADMIN", "DISTRICT_ADMIN"];

export type User = {
  id: string;
  email: string;
  full_name: string;
  role: Role;
  organization_id: string | null;
  organization_name: string | null;
  state_code: string | null;
  district_code: string | null;
  is_active: boolean;
};

export type AuthResponse = {
  access_token: string;
  token_type: "bearer";
  expires_in: number;
  user: User;
};

export type RegisterRequest = {
  organization_name: string;
  registration_number?: string;
  address?: string;
  state_code: string;
  district_code: string;
  full_name: string;
  email: string;
  phone?: string;
  password: string;
};
