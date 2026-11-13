import { describe, expect, it } from "vitest";
import { formatAmount, formatDate, formatScore, formatValue } from "./format";

describe("formatAmount", () => {
  it.each([
    ["12450000.00", "12.450.000,00"],
    ["3552000", "3.552.000"],
    ["999", "999"],
    ["1000", "1.000"],
    ["0", "0"],
    ["0.10", "0,10"],
    ["-1500.5", "-1.500,5"],
    ["-0", "-0"],
    ["1000000000000", "1.000.000.000.000"],
    ["007", "7"],
  ])("%s -> %s", (input, out) => expect(formatAmount(input)).toBe(out));

  it("tidak membulatkan angka besar (tidak lewat float)", () => {
    expect(formatAmount("123456789012345678.99")).toBe("123.456.789.012.345.678,99");
  });

  it.each(["", "abc", "1,000", "1.2.3", " "])("teks tidak valid dikembalikan apa adanya: %j", (v) => {
    expect(formatAmount(v)).toBe(v);
  });
});

describe("formatDate", () => {
  it("format Indonesia", () => expect(formatDate("2024-03-05")).toBe("5 Mar 2024"));
  it("Agustus dan Desember", () => {
    expect(formatDate("2024-08-17")).toBe("17 Agu 2024");
    expect(formatDate("2024-12-31")).toBe("31 Des 2024");
  });
  it("bulan tidak valid tetap mentah", () => expect(formatDate("2024-13-01")).toBe("2024-13-01"));
  it("bukan tanggal", () => expect(formatDate("kemarin")).toBe("kemarin"));
});

describe("formatValue & formatScore", () => {
  it("memilih format sesuai jenis", () => {
    expect(formatValue("amount", "1000")).toBe("1.000");
    expect(formatValue("date", "2024-03-05")).toBe("5 Mar 2024");
    expect(formatValue("doc_id", "KW-2024/0815")).toBe("KW-2024/0815");
  });
  it("skor", () => {
    expect(formatScore(0.976)).toBe("98%");
    expect(formatScore(null)).toBe("–");
    expect(formatScore(0)).toBe("0%");
  });
});
