import type { Field, FieldKind, Flag, PageState } from "../api/types";

export const KIND_LABEL: Record<FieldKind, string> = {
  doc_id: "Nomor dokumen",
  amount: "Nominal",
  date: "Tanggal",
};

export type PageFilter = "semua" | "ragu" | "belum" | "selesai";

export const FILTER_LABEL: Record<PageFilter, string> = {
  semua: "Semua",
  ragu: "Ada keraguan",
  belum: "Belum dicek",
  selesai: "Dikonfirmasi",
};

/** Semua indikator keraguan di satu foto: tingkat halaman + tiap nilai. */
export function pageDoubts(page: PageState): Flag[] {
  return [...page.flags, ...page.fields.flatMap((f) => f.flags)];
}

export function hasDoubt(page: PageState): boolean {
  return pageDoubts(page).length > 0;
}

export function isCorrected(field: Field): boolean {
  return field.history.some((h) => h.action === "correct");
}

export function filterPages(pages: PageState[], filter: PageFilter): PageState[] {
  switch (filter) {
    case "semua":
      return pages;
    case "ragu":
      return pages.filter((p) => p.status !== "dikonfirmasi" && hasDoubt(p));
    case "belum":
      return pages.filter((p) => p.status !== "dikonfirmasi");
    case "selesai":
      return pages.filter((p) => p.status === "dikonfirmasi");
  }
}

export function summarize(pages: PageState[]) {
  const confirmed = pages.filter((p) => p.status === "dikonfirmasi").length;
  return {
    total: pages.length,
    confirmed,
    doubtful: pages.filter((p) => p.status !== "dikonfirmasi" && hasDoubt(p)).length,
    open: pages.length - confirmed,
  };
}

const KIND_ORDER: Record<FieldKind, number> = { doc_id: 0, date: 1, amount: 2 };

/** Urutan di ledger: nomor dokumen, tanggal, nominal (total dulu). Urutan stabil. */
export function sortFields(fields: Field[]): Field[] {
  return [...fields].sort(
    (a, b) =>
      KIND_ORDER[a.kind] - KIND_ORDER[b.kind] ||
      Number(b.label === "total") - Number(a.label === "total") ||
      a.id - b.id,
  );
}

/** Foto berikut/sebelumnya di daftar yang sedang tampil. */
export function stepPage(pages: PageState[], current: string | null, dir: 1 | -1): string | null {
  if (pages.length === 0) return null;
  const i = pages.findIndex((p) => p.sha256 === current);
  if (i === -1) return pages[0]!.sha256;
  const next = pages[Math.min(pages.length - 1, Math.max(0, i + dir))];
  return next ? next.sha256 : null;
}

/** Foto berikut yang belum dikonfirmasi, mulai setelah foto ini (berputar). */
export function nextOpenPage(pages: PageState[], current: string): string | null {
  const i = pages.findIndex((p) => p.sha256 === current);
  for (let k = 1; k <= pages.length; k++) {
    const p = pages[(i + k) % pages.length]!;
    if (p.status !== "dikonfirmasi" && p.sha256 !== current) return p.sha256;
  }
  return null;
}
