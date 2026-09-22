import type { components } from "./api-types";

// Types come from FastAPI's OpenAPI schema (`npm run gen:api` regenerates lib/api-types.ts).
type Schemas = components["schemas"];

export type Role = Schemas["Role"];
export type User = Schemas["UserOut"];
export type TokenResponse = Schemas["TokenResponse"];
export type SchoolSettings = Schemas["SchoolSettingsOut"];
export type PublicConfig = Schemas["PublicConfig"];

/** Matches the backend `Page[T]` envelope used by every list endpoint. */
export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}
