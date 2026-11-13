/** Gabung folder sumber (format OS) dengan path relatif dari mesin (selalu pakai "/"). */
export function joinPath(base: string, rel: string): string {
  const sep = base.includes("\\") && !base.includes("/") ? "\\" : "/";
  const trimmed = base.replace(/[\\/]+$/, "");
  return [trimmed, ...rel.split("/").filter(Boolean)].join(sep);
}

/** Nama file terakhir dari path relatif. */
export function baseName(rel: string): string {
  return rel.split(/[\\/]/).pop() ?? rel;
}

/** Folder induk dari path relatif ("" kalau di akar). */
export function dirName(rel: string): string {
  const parts = rel.split("/");
  parts.pop();
  return parts.join("/");
}
