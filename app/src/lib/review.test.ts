import { describe, expect, it } from "vitest";
import type { Field, PageState } from "../api/types";
import { filterPages, nextOpenPage, sortFields, stepPage, summarize } from "./review";

const flag = { code: "LOW_CONFIDENCE", message: "x" };

function field(id: number, kind: Field["kind"], extra: Partial<Field> = {}): Field {
  return {
    id, kind, value: "1", key: "1", raw: "1", line: 0, label: "", score: 0.99, flags: [],
    original: "1", source: "ocr", history: [], ...extra,
  };
}

function page(sha: string, extra: Partial<PageState> = {}): PageState {
  return { sha256: sha, files: [`${sha}.jpg`], flags: [], status: "belum_dicek", fields: [], ...extra };
}

const pages = [
  page("a"),
  page("b", { flags: [flag] }),
  page("c", { status: "dikonfirmasi", flags: [flag] }),
  page("d", { fields: [field(0, "amount", { flags: [flag] })] }),
];

describe("filterPages", () => {
  it("ragu = belum dikonfirmasi DAN ada indikator (halaman atau nilai)", () => {
    expect(filterPages(pages, "ragu").map((p) => p.sha256)).toEqual(["b", "d"]);
  });
  it("belum dan selesai saling melengkapi", () => {
    expect(filterPages(pages, "belum").map((p) => p.sha256)).toEqual(["a", "b", "d"]);
    expect(filterPages(pages, "selesai").map((p) => p.sha256)).toEqual(["c"]);
  });
  it("kosong", () => expect(filterPages([], "ragu")).toEqual([]));
});

describe("summarize", () => {
  it("menghitung", () => expect(summarize(pages)).toEqual({ total: 4, confirmed: 1, doubtful: 2, open: 3 }));
  it("kosong", () => expect(summarize([])).toEqual({ total: 0, confirmed: 0, doubtful: 0, open: 0 }));
});

describe("sortFields", () => {
  it("nomor, tanggal, lalu nominal dengan total di atas; stabil", () => {
    const sorted = sortFields([
      field(0, "amount"), field(1, "date"), field(2, "amount", { label: "total" }), field(3, "doc_id"), field(4, "doc_id"),
    ]);
    expect(sorted.map((f) => f.id)).toEqual([3, 4, 1, 2, 0]);
  });
});

describe("navigasi", () => {
  it("stepPage berhenti di ujung", () => {
    expect(stepPage(pages, "a", -1)).toBe("a");
    expect(stepPage(pages, "d", 1)).toBe("d");
    expect(stepPage(pages, "b", 1)).toBe("c");
    expect(stepPage(pages, null, 1)).toBe("a");
    expect(stepPage([], "a", 1)).toBeNull();
  });
  it("nextOpenPage melewati yang sudah dikonfirmasi dan berputar", () => {
    expect(nextOpenPage(pages, "b")).toBe("d");
    expect(nextOpenPage(pages, "d")).toBe("a");
    expect(nextOpenPage([page("x", { status: "dikonfirmasi" })], "x")).toBeNull();
  });
});
