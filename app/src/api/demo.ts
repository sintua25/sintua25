// Mode demo: data hasil mesin sungguhan atas foto sintetis (src/demo/data.json), disimpan di memori.
// Dipakai saat UI dibuka di browser biasa (tanpa Tauri) dan untuk tes. Aturan koreksi meniru mesin.
import data from "../demo/data.json";
import type { Api } from "./api";
import type { ApiError, Field, PageDetail, PageState, ReviewState, Session } from "./types";

const fail = (code: string, message: string, hint = ""): ApiError => ({ code, message, hint });
const clone = <T,>(v: T): T => JSON.parse(JSON.stringify(v)) as T;
const now = () => new Date().toISOString();
const wait = (ms: number) => new Promise((r) => setTimeout(r, ms));

export function createDemoApi(): Api {
  let pages: PageState[] = clone(data.pages as PageState[]);
  const details = data.details as unknown as Record<string, PageDetail>;
  let seq = 0;

  const find = (sha: string) => {
    const p = pages.find((x) => x.sha256 === sha);
    if (!p) throw fail("PAGE_NOT_FOUND", "Foto tidak ada di folder kerja ini.", "Muat ulang data.");
    return p;
  };
  const needReason = (reason: string) => {
    if (!reason.trim()) throw fail("REASON_REQUIRED", "Alasan wajib diisi.", "Tulis singkat kenapa nilai diubah.");
  };
  const needOpen = (p: PageState) => {
    if (p.status === "dikonfirmasi")
      throw fail("CONFIRMED_LOCKED", "Foto ini sudah dikonfirmasi, nilainya terkunci.", "Batalkan konfirmasi dulu (dengan alasan), baru koreksi.");
  };
  const normalize = (kind: Field["kind"], value: string) => {
    const v = value.trim();
    if (!v) throw fail("EMPTY_VALUE", "Nilai baru kosong.", "Isi nilai yang benar sesuai dokumen fisik.");
    if (kind === "amount") {
      if (!/^-?(rp\.?\s*)?[\d.,]+$/i.test(v)) throw fail("BAD_AMOUNT", `'${v}' bukan nominal.`, "Tulis seperti 12.450.000,00.");
      return v.replace(/^rp\.?\s*/i, "").replace(/\./g, "").replace(",", ".");
    }
    if (kind === "date") {
      const m = /^(\d{1,2})\/(\d{1,2})\/(\d{4})$/.exec(v);
      if (m) return `${m[3]}-${m[2]!.padStart(2, "0")}-${m[1]!.padStart(2, "0")}`;
      if (!/^\d{4}-\d{2}-\d{2}$/.test(v)) throw fail("BAD_DATE", `'${v}' bukan tanggal yang valid.`, "Tulis seperti 31/12/2024.");
    }
    return v;
  };
  const entry = (action: string, before: unknown, after: unknown, reason: string) => ({
    seq: ++seq, ts: now(), actor: "demo", action, before, after, reason,
  });

  return {
    mode: "demo",
    chooseFolder: async () => data.source,
    startupFolder: async () => data.source,
    openSource: async (source): Promise<Session> => ({ source, workspace: "(demo, tersimpan di memori)" }),
    async process(_s, onEvent) {
      onEvent({ type: "start", source: data.source, total: pages.length });
      let n = 0;
      for (const p of pages) {
        await wait(250);
        onEvent({ type: "skipped", n: ++n, file: p.files[0]!, sha256: p.sha256, reason: "sudah diproses" });
      }
      onEvent({ type: "done", processed: 0, skipped: pages.length, failed: 0, elapsed_s: 1 });
    },
    state: async (): Promise<ReviewState> => ({ source: data.source, pages: clone(pages) }),
    async page(_s, sha) {
      const d = details[sha];
      if (!d) throw fail("PAGE_NOT_FOUND", "Hasil OCR tidak ada.", "Proses ulang folder ini.");
      return d;
    },
    imageUrl: (_s, rel) => `/demo/${rel.split("/").map(encodeURIComponent).join("/")}`,
    workspaceUrl: () => "", // data demo hanya berisi foto
    async correct(_s, sha, id, value, reason, expected) {
      const p = find(sha);
      const f = p.fields[id];
      if (!f) throw fail("FIELD_NOT_FOUND", "Nilai tidak ada.", "Muat ulang data.");
      if (expected !== f.value) throw fail("STALE", "Nilai sudah berubah sejak layar dibuka.", "Muat ulang.");
      const v = normalize(f.kind, value);
      if (v === f.value) throw fail("NO_CHANGE", "Nilai baru sama dengan nilai sekarang.", "Tidak ada yang disimpan.");
      needReason(reason);
      needOpen(p);
      f.history.push(entry("correct", f.value, v, reason.trim()));
      f.value = v;
      f.key = v;
    },
    async addField(_s, sha, kind, value, reason, line) {
      const p = find(sha);
      needReason(reason);
      needOpen(p);
      const v = normalize(kind, value);
      const raw = line !== undefined ? details[sha]?.lines[line]?.text ?? "" : "";
      p.fields.push({
        id: p.fields.length, kind, value: v, key: v, raw, line: line ?? null, label: "", score: null, flags: [],
        original: null, source: "auditor", history: [entry("add_field", null, { kind, value: v }, reason.trim())],
      });
    },
    async confirm(_s, sha) {
      const p = find(sha);
      if (p.status === "dikonfirmasi") throw fail("ALREADY_CONFIRMED", "Foto ini sudah dikonfirmasi.");
      p.status = "dikonfirmasi";
    },
    async unconfirm(_s, sha, reason) {
      const p = find(sha);
      needReason(reason);
      p.status = "belum_dicek";
    },
    verify: async () => ({ ok: true, entries: seq, pages_checked: pages.length, last_hash: "demo", problems: [] }),
    openOutput: async () => undefined, // mode demo tidak punya folder hasil
    // Mode demo tidak menulis file; hanya menunjukkan bentuk hasilnya.
    exportFiles: async (s) => ({
      files: [
        { path: `${s.workspace}/export/vouching-demo.json`, sha256: "demo" },
        { path: `${s.workspace}/export/vouching-demo.xlsx`, sha256: "demo" },
      ],
      pages: pages.length,
      confirmed: pages.filter((p) => p.status === "dikonfirmasi").length,
    }),
  };
}
