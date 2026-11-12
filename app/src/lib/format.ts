// Format tampilan saja. Nilai disimpan dan dibandingkan sebagai string desimal; tidak ada float.

const DECIMAL = /^(-?)(\d+)(?:\.(\d+))?$/;

/** "12450000.00" -> "12.450.000,00"; "-1500" -> "-1.500". Teks tidak valid dikembalikan apa adanya. */
export function formatAmount(value: string): string {
  const m = DECIMAL.exec(value.trim());
  if (!m) return value;
  const [, sign, int = "0", frac] = m;
  const grouped = int.replace(/^0+(?=\d)/, "").replace(/\B(?=(\d{3})+(?!\d))/g, ".");
  return `${sign}${grouped}${frac !== undefined ? `,${frac}` : ""}`;
}

/** "2024-03-12" -> "12 Mar 2024". */
export function formatDate(iso: string): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso);
  if (!m) return iso;
  const months = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"];
  const month = months[Number(m[2]) - 1];
  return month ? `${Number(m[3])} ${month} ${m[1]}` : iso;
}

export function formatValue(kind: string, value: string): string {
  if (kind === "amount") return formatAmount(value);
  if (kind === "date") return formatDate(value);
  return value;
}

/** 0.9876 -> "99%"; null -> "–". */
export function formatScore(score: number | null): string {
  return score === null ? "–" : `${Math.round(score * 100)}%`;
}

/** ISO dengan zona -> "12 Mar 2024 14.05" (waktu lokal). */
export function formatTimestamp(ts: string): string {
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return ts;
  const date = formatDate(
    `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`,
  );
  return `${date} ${String(d.getHours()).padStart(2, "0")}.${String(d.getMinutes()).padStart(2, "0")}`;
}
