// Bentuk data persis seperti keluaran CLI `vouchocr` (engine/vouchocr/workspace.py, pipeline.py).
// Nominal SELALU string desimal ("12450000.00"), tidak pernah number, supaya tidak ada pembulatan float.

export type FieldKind = "doc_id" | "amount" | "date";
export type PageStatus = "belum_dicek" | "dikonfirmasi";

export interface Flag {
  code: string;
  message: string;
  [extra: string]: unknown;
}

export interface HistoryEntry {
  seq: number;
  ts: string;
  actor: string;
  action: string;
  before: unknown;
  after: unknown;
  reason: string;
}

export interface Field {
  id: number;
  kind: FieldKind;
  value: string;
  key: string;
  raw: string;
  line: number | null;
  label: string;
  score: number | null;
  flags: Flag[];
  original: string | null;
  source: "ocr" | "auditor";
  history: HistoryEntry[];
}

export interface PageState {
  sha256: string;
  files: string[];
  flags: Flag[];
  status: PageStatus;
  fields: Field[];
}

export interface ReviewState {
  source: string;
  pages: PageState[];
}

export type Point = [number, number];

export interface OcrLine {
  text: string;
  score: number;
  box: Point[];
  reread: string | null;
  reread_score: number | null;
}

export interface PageDetail {
  file: string;
  sha256: string;
  size: [number, number];
  lines: OcrLine[];
  preprocess: Record<string, unknown>;
}

export type ProcessEvent =
  | { type: "start"; source: string; total: number }
  | { type: "page"; n: number; file: string; sha256: string; fields: number; flags: string[]; elapsed_ms: number }
  | { type: "skipped"; n: number; file: string; sha256: string; reason: string }
  | { type: "error"; n?: number; file?: string; code: string; message: string; hint: string }
  | { type: "done"; processed: number; skipped: number; failed: number; elapsed_s: number };

export interface VerifyResult {
  ok: boolean;
  entries: number;
  pages_checked: number;
  last_hash: string;
  problems: string[];
}

export interface Session {
  source: string;
  workspace: string;
}

/** Galat yang bisa ditindaklanjuti: apa yang terjadi + apa yang bisa dilakukan. */
export interface ApiError {
  code: string;
  message: string;
  hint: string;
}

export function isApiError(e: unknown): e is ApiError {
  return typeof e === "object" && e !== null && "code" in e && "message" in e;
}
