import { useEffect, useState } from "react";
import type { ApiError, Field, FieldKind, PageDetail, PageState } from "../api/types";
import { isApiError } from "../api/types";
import { formatScore, formatTimestamp, formatValue } from "../lib/format";
import { KIND_LABEL, isCorrected, sortFields } from "../lib/review";
import { Tick } from "./icons";

export interface LedgerActions {
  correct: (field: Field, value: string, reason: string) => Promise<void>;
  addField: (kind: FieldKind, value: string, reason: string) => Promise<void>;
  confirm: () => Promise<void>;
  unconfirm: (reason: string) => Promise<void>;
  next: () => void;
}

interface Props {
  page: PageState;
  detail: PageDetail | null;
  selectedField: number | null;
  onSelectField: (id: number | null) => void;
  actions: LedgerActions;
  hasNext: boolean;
}

export function Ledger({ page, detail, selectedField, onSelectField, actions, hasNext }: Props) {
  const fields = sortFields(page.fields);
  const selected = page.fields.find((f) => f.id === selectedField) ?? null;
  const locked = page.status === "dikonfirmasi";

  return (
    <aside className="pane" aria-label="Ledger">
      <div className="ledger-head">
        <h2>Ledger foto ini</h2>
        <div className="meta">
          {page.fields.length} nilai terbaca · {locked ? "dikonfirmasi" : "belum dicek"}
        </div>
      </div>
      <div className="ledger-scroll">
        {page.flags.map((f, i) => <div key={i} className="note">{f.message}</div>)}
        <table className="ledger">
          <thead>
            <tr><th>Jenis</th><th>Nilai</th><th>Yakin</th></tr>
          </thead>
          <tbody>
            {fields.map((f) => (
              <tr key={f.id} className="ledger-row" tabIndex={0} aria-selected={f.id === selectedField}
                onClick={() => onSelectField(f.id === selectedField ? null : f.id)}
                onKeyDown={(e) => e.key === "Enter" && onSelectField(f.id)}>
                <td className="kind">{KIND_LABEL[f.kind]}{f.label && f.label !== "nomor" && f.label !== "tanggal" && <small>{f.label}</small>}</td>
                <td className="value"><FieldValue field={f} /></td>
                <td className="score">{formatScore(f.score)}</td>
              </tr>
            ))}
            {fields.length === 0 && (
              <tr><td colSpan={3} className="kind">Tidak ada nilai yang terbaca. Tambahkan manual dari dokumen fisik.</td></tr>
            )}
          </tbody>
        </table>
        {selected ? (
          <CorrectionPanel key={`${page.sha256}:${selected.id}`} field={selected} detail={detail} locked={locked} onSave={actions.correct} />
        ) : (
          !locked && <AddFieldPanel key={page.sha256} onSave={actions.addField} />
        )}
      </div>
      <ConfirmBar key={page.sha256} page={page} actions={actions} hasNext={hasNext} />
    </aside>
  );
}

function FieldValue({ field }: { field: Field }) {
  const shown = formatValue(field.kind, field.value);
  return (
    <>
      {isCorrected(field) && field.original !== null && (
        <span className="struck">{formatValue(field.kind, field.original)}</span>
      )}
      {field.flags.length > 0 && !isCorrected(field) ? <span className="marked">{shown}</span> : shown}
      {isCorrected(field) && <span className="by-hand">dikoreksi</span>}
      {field.source === "auditor" && <span className="by-hand">ditambah</span>}
    </>
  );
}

function editable(field: Field): string {
  if (field.kind === "amount") return formatValue("amount", field.value);
  if (field.kind === "date") {
    const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(field.value);
    return m ? `${m[3]}/${m[2]}/${m[1]}` : field.value;
  }
  return field.value;
}

function useSubmit() {
  const [error, setError] = useState<ApiError | null>(null);
  const [busy, setBusy] = useState(false);
  const run = async (fn: () => Promise<void>) => {
    setBusy(true);
    setError(null);
    try {
      await fn();
      return true;
    } catch (e) {
      setError(isApiError(e) ? e : { code: "UNKNOWN", message: String(e), hint: "" });
      return false;
    } finally {
      setBusy(false);
    }
  };
  return { error, busy, run };
}

function ErrorNote({ error }: { error: ApiError | null }) {
  if (!error) return null;
  return (
    <div className="note note-error" role="alert" style={{ margin: 0 }}>
      {error.message}
      {error.hint && <span className="hint">{error.hint}</span>}
    </div>
  );
}

function CorrectionPanel({ field, detail, locked, onSave }: {
  field: Field; detail: PageDetail | null; locked: boolean; onSave: LedgerActions["correct"];
}) {
  const [value, setValue] = useState(editable(field));
  const [reason, setReason] = useState("");
  const { error, busy, run } = useSubmit();
  const line = field.line !== null ? detail?.lines[field.line] : undefined;
  useEffect(() => setValue(editable(field)), [field]);

  const unchanged = value.trim() === editable(field);
  return (
    <form className="panel" onSubmit={async (e) => {
      e.preventDefault();
      if (await run(() => onSave(field, value, reason))) setReason("");
    }}>
      <h3>{KIND_LABEL[field.kind]}</h3>
      {field.source === "ocr" ? (
        <div className="read">
          Terbaca dari foto: <span className="mono">{field.raw || "–"}</span>
          {line && <><br />Baris teks: <span className="mono">{line.text}</span></>}
          {line?.reread && line.reread !== line.text && <><br />Dibaca ulang: <span className="mono">{line.reread}</span></>}
        </div>
      ) : (
        <div className="read">Ditambahkan auditor, tidak ada di hasil OCR.</div>
      )}
      {field.flags.length > 0 && <ul>{field.flags.map((f, i) => <li key={i}>{f.message}</li>)}</ul>}
      {locked ? (
        <div className="read">Foto sudah dikonfirmasi. Batalkan konfirmasi dulu untuk mengoreksi.</div>
      ) : (
        <>
          <label>Nilai benar
            <input className="mono" value={value} onChange={(e) => setValue(e.target.value)} spellCheck={false} />
          </label>
          <label>Alasan koreksi
            <textarea value={reason} onChange={(e) => setReason(e.target.value)}
              placeholder="Misal: angka 8 terbaca 3, sudah dicek ke dokumen fisik" />
          </label>
          <ErrorNote error={error} />
          <div className="row">
            <button className="btn btn-ink" type="submit" disabled={busy || unchanged || !reason.trim()}>Simpan koreksi</button>
          </div>
        </>
      )}
      {field.history.length > 0 && (
        <ul className="history" aria-label="Riwayat">
          {field.history.map((h) => (
            <li key={h.seq}>
              <span className="mono">#{h.seq}</span> {formatTimestamp(h.ts)} · {h.actor}: {describe(field.kind, h)}
              {h.reason && <> · “{h.reason}”</>}
            </li>
          ))}
        </ul>
      )}
    </form>
  );
}

function describe(kind: FieldKind, h: Field["history"][number]): string {
  if (h.action === "add_field") return "menambah nilai";
  const fmt = (v: unknown) => (typeof v === "string" ? formatValue(kind, v) : "–");
  return `${fmt(h.before)} → ${fmt(h.after)}`;
}

function AddFieldPanel({ onSave }: { onSave: LedgerActions["addField"] }) {
  const [open, setOpen] = useState(false);
  const [kind, setKind] = useState<FieldKind>("doc_id");
  const [value, setValue] = useState("");
  const [reason, setReason] = useState("");
  const { error, busy, run } = useSubmit();

  if (!open) {
    return (
      <div className="panel">
        <div className="read">Pilih baris ledger atau kotak di foto untuk mengoreksi.</div>
        <div><button className="link" onClick={() => setOpen(true)}>Tambah nilai yang tidak terbaca</button></div>
      </div>
    );
  }
  return (
    <form className="panel" onSubmit={async (e) => {
      e.preventDefault();
      if (await run(() => onSave(kind, value, reason))) {
        setOpen(false);
        setValue("");
        setReason("");
      }
    }}>
      <h3>Tambah nilai</h3>
      <label>Jenis
        <select value={kind} onChange={(e) => setKind(e.target.value as FieldKind)}>
          {(Object.keys(KIND_LABEL) as FieldKind[]).map((k) => <option key={k} value={k}>{KIND_LABEL[k]}</option>)}
        </select>
      </label>
      <label>Nilai
        <input className="mono" value={value} onChange={(e) => setValue(e.target.value)}
          placeholder={kind === "amount" ? "12.450.000,00" : kind === "date" ? "31/12/2024" : "KW-2024/0815"} />
      </label>
      <label>Alasan
        <textarea value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Misal: tulisan tangan, tidak terbaca OCR" />
      </label>
      <ErrorNote error={error} />
      <div className="row">
        <button className="btn btn-ink" type="submit" disabled={busy || !value.trim() || !reason.trim()}>Simpan nilai</button>
        <button className="link" type="button" onClick={() => setOpen(false)}>Batal</button>
      </div>
    </form>
  );
}

function ConfirmBar({ page, actions, hasNext }: { page: PageState; actions: LedgerActions; hasNext: boolean }) {
  const [justConfirmed, setJustConfirmed] = useState(false);
  const [undoing, setUndoing] = useState(false);
  const [reason, setReason] = useState("");
  const { error, busy, run } = useSubmit();

  if (page.status !== "dikonfirmasi") {
    return (
      <div className="confirm-bar">
        <button className="btn btn-ink" disabled={busy} onClick={async () => {
          if (await run(actions.confirm)) setJustConfirmed(true);
        }}>Konfirmasi foto</button>
        <span className="read" style={{ color: "var(--ink-soft)", fontSize: 12.5 }}>Semua nilai sudah dicek ke foto</span>
        <ErrorNote error={error} />
      </div>
    );
  }
  if (undoing) {
    return (
      <form className="confirm-bar panel" style={{ display: "grid" }} onSubmit={async (e) => {
        e.preventDefault();
        if (await run(() => actions.unconfirm(reason))) {
          setUndoing(false);
          setJustConfirmed(false);
        }
      }}>
        <label>Alasan membatalkan konfirmasi
          <input value={reason} onChange={(e) => setReason(e.target.value)} autoFocus />
        </label>
        <ErrorNote error={error} />
        <div className="row">
          <button className="btn" type="submit" disabled={busy || !reason.trim()}>Batalkan konfirmasi</button>
          <button className="link" type="button" onClick={() => setUndoing(false)}>Tutup</button>
        </div>
      </form>
    );
  }
  return (
    <div className="confirm-bar">
      <span className="confirmed"><Tick draw={justConfirmed} size={20} />Foto dikonfirmasi</span>
      {hasNext && <button className="btn" onClick={actions.next}>Foto berikut</button>}
      <button className="link" style={{ marginLeft: "auto" }} onClick={() => setUndoing(true)}>Batalkan konfirmasi</button>
    </div>
  );
}
