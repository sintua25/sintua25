import { useEffect, useRef, useState } from "react";
import type { PageDetail, PageState } from "../api/types";
import { polygonPoints } from "../lib/geometry";
import { baseName } from "../lib/paths";

interface Props {
  page: PageState;
  detail: PageDetail | null;
  imageUrl: string;
  selectedField: number | null;
  onSelectField: (id: number) => void;
  /** Baris teks yang dipilih dari "Teks lengkap" (tanpa nilai). */
  selectedLine: number | null;
  onSelectLine: (line: number) => void;
}

export function PhotoView({ page, detail, imageUrl, selectedField, onSelectField, selectedLine, onSelectLine }: Props) {
  const desk = useRef<HTMLDivElement>(null);
  const [avail, setAvail] = useState({ w: 800, h: 600 });
  const [fit, setFit] = useState(true);
  const [allLines, setAllLines] = useState(false);
  const [imgFailed, setImgFailed] = useState(false);

  useEffect(() => {
    const el = desk.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => e && setAvail({ w: e.contentRect.width, h: e.contentRect.height }));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  useEffect(() => setImgFailed(false), [imageUrl]);

  const [w, h] = detail?.size ?? [0, 0];
  const width = !w ? undefined : fit ? Math.min(avail.w, (avail.h * w) / h) : w;

  // Baris sumber tiap nilai -> warna kotak.
  const lineFields = new Map<number, { ids: number[]; doubt: boolean }>();
  for (const f of page.fields) {
    if (f.line === null) continue;
    const entry = lineFields.get(f.line) ?? { ids: [], doubt: false };
    entry.ids.push(f.id);
    entry.doubt ||= f.flags.length > 0;
    lineFields.set(f.line, entry);
  }
  const activeLine = selectedLine ?? page.fields.find((f) => f.id === selectedField)?.line ?? null;
  const file = page.files[0] ?? "";

  return (
    <section className="pane" aria-label="Foto">
      <div className="viewer-bar">
        <span className="title" title={file}>{baseName(file)}</span>
        <label className="toggle">
          <input type="checkbox" checked={allLines} onChange={(e) => setAllLines(e.target.checked)} />
          Semua baris teks
        </label>
        <button className="btn" onClick={() => setFit(!fit)}>{fit ? "Ukuran asli" : "Pas layar"}</button>
      </div>
      <div className="desk" ref={desk}>
        {page.source_kind === "docx_text" ? (
          <TextPage lines={detail?.lines.map((l) => l.text) ?? []} lineFields={lineFields} activeLine={activeLine}
            onSelectField={onSelectField} onSelectLine={onSelectLine} />
        ) : imgFailed ? (
          <div className="note note-error">
            Foto tidak bisa ditampilkan.
            <span className="hint">Mungkin file dipindah atau diganti nama setelah diproses. Pilih ulang folder sumbernya.</span>
          </div>
        ) : (
          <div className="sheet" style={{ width }}>
            <img src={imageUrl} alt={`Foto ${baseName(file)}`} onError={() => setImgFailed(true)} draggable={false} />
            {detail && (
              <svg viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" role="img" aria-label="Kotak hasil OCR">
                {detail.lines.map((line, i) => {
                  const fields = lineFields.get(i);
                  if (!fields && !allLines && i !== activeLine) return null;
                  const cls = ["box-line", fields && "box-field", fields?.doubt && "box-doubt", i === activeLine && "box-active"]
                    .filter(Boolean)
                    .join(" ");
                  return (
                    <polygon key={i} className={cls} points={polygonPoints(line.box)}
                      onClick={() => (fields ? onSelectField(fields.ids[0]!) : onSelectLine(i))}>
                      <title>{line.text}</title>
                    </polygon>
                  );
                })}
              </svg>
            )}
          </div>
        )}
      </div>
    </section>
  );
}

/** Teks dari Word: dibaca langsung tanpa OCR, jadi yang ditampilkan adalah barisnya. */
function TextPage({ lines, lineFields, activeLine, onSelectField, onSelectLine }: {
  lines: string[];
  lineFields: Map<number, { ids: number[]; doubt: boolean }>;
  activeLine: number | null;
  onSelectField: (id: number) => void;
  onSelectLine: (line: number) => void;
}) {
  return (
    <ol className="textpage" aria-label="Teks dokumen Word">
      {lines.map((text, i) => {
        const f = lineFields.get(i);
        const cls = [f && "has-field", f?.doubt && "doubt", i === activeLine && "active"].filter(Boolean).join(" ");
        return (
          <li key={i} className={cls || undefined}>
            <button className="textline" onClick={() => (f ? onSelectField(f.ids[0]!) : onSelectLine(i))}>{text}</button>
          </li>
        );
      })}
    </ol>
  );
}
