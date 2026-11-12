import type { FieldKind, PageDetail, ProcessEvent, ReviewState, Session, VerifyResult } from "./types";

/** Semua yang dibutuhkan UI dari mesin. Implementasi: Tauri (desktop) dan demo (browser/tes). */
export interface Api {
  readonly mode: "desktop" | "demo";
  chooseFolder(): Promise<string | null>;
  /** Folder yang diberikan saat aplikasi dibuka (argumen baris perintah), kalau ada. */
  startupFolder(): Promise<string | null>;
  openSource(source: string): Promise<Session>;
  process(session: Session, onEvent: (e: ProcessEvent) => void): Promise<void>;
  state(session: Session): Promise<ReviewState>;
  page(session: Session, sha: string): Promise<PageDetail>;
  imageUrl(session: Session, relFile: string): string;
  correct(session: Session, sha: string, field: number, value: string, reason: string, expected: string): Promise<void>;
  addField(session: Session, sha: string, kind: FieldKind, value: string, reason: string): Promise<void>;
  confirm(session: Session, sha: string): Promise<void>;
  unconfirm(session: Session, sha: string, reason: string): Promise<void>;
  verify(session: Session): Promise<VerifyResult>;
}
