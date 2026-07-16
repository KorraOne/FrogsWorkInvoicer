export type Screen = "welcome" | "upgrade" | "app";

export interface MobileAccount {
  email: string;
  active: boolean;
  storage_tier: "local" | "cloud";
  portal_url: string | null;
  email_verified: boolean;
}

export interface SessionTokens {
  access_token: string;
  refresh_token?: string;
}

export interface AppContext {
  account: MobileAccount | null;
  onSyncStatus: (text: string) => void;
}

export type InvoiceRecord = Record<string, unknown> & {
  invoice_id?: string;
  invoice_number: number;
  invoice_date?: string;
  customer_name?: string;
  business_name?: string;
  status?: string;
  total_inc_gst?: number | string;
  deleted_at?: string;
  line_items?: Array<Record<string, unknown>>;
};

export type EntityMap = Record<string, Record<string, unknown>>;
