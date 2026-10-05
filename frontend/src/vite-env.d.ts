/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Public base URL of the FastAPI backend (no secrets: VITE_ variables are bundled into the client). */
  readonly VITE_API_BASE_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
