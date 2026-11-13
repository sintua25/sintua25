import { useCallback, useEffect, useMemo, useState } from "react";
import type { Api } from "./api/api";
import type { ApiError, ExportResult, PageDetail, ReviewState, Session, VerifyResult } from "./api/types";
import { isApiError } from "./api/types";
import { Ledger, type LedgerActions } from "./components/Ledger";
import { PhotoList } from "./components/PhotoList";
import { PhotoView } from "./components/PhotoView";
import { TopBar } from "./components/TopBar";
import { filterPages, nextOpenPage, type PageFilter, stepPage } from "./lib/review";

interface Progress { done: number; total: number; failed: { file: string; message: string }[] }

const asError = (e: unknown): ApiError =>
  isApiError(e) ? e : { code: "UNKNOWN", message: String(e), hint: "Coba lagi. Kalau terus terjadi, catat pesan ini." };

export function App({ api }: { api: Api }) {
  const [session, setSession] = useState<Session | null>(null);
  const [review, setReview] = useState<ReviewState | null>(null);
  const [filter, setFilter] = useState<PageFilter>("semua");
  const [selected, setSelected] = useState<string | null>(null);
  const [detail, setDetail] = useState<PageDetail | null>(null);
  const [field, setField] = useState<number | null>(null);
  const [line, setLine] = useState<number | null>(null);
  const [progress, setProgress] = useState<Progress | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [verify, setVerify] = useState<VerifyResult | null>(null);
  const [exported, setExported] = useState<ExportResult | null>(null);
  const [toast, setToast] = useState<string | null>(null);

  const pages = useMemo(() => review?.pages ?? [], [review]);
  const shown = useMemo(() => filterPages(pages, filter), [pages, filter]);
  const page = pages.find((p) => p.sha256 === selected) ?? null;

  const say = (msg: string) => {
    setToast(msg);
    window.setTimeout(() => setToast((t) => (t === msg ? null : t)), 2200);
  };

  const refresh = useCallback(async (s: Session) => {
    const st = await api.state(s);
    setReview(st);
    setSelected((cur) => cur ?? st.pages[0]?.sha256 ?? null);
  }, [api]);

  const runProcess = useCallback(async (s: Session) => {
    setBusy(true);
    setError(null);
    setVerify(null);
    const p: Progress = { done: 0, total: 0, failed: [] };
    setProgress({ ...p });
    try {
      await api.process(s, (e) => {
        if (e.type === "start") p.total = e.total;
        else if (e.type === "page" || e.type === "skipped") p.done = e.n;
        else if (e.type === "error") {
          if (e.n) p.done = e.n;
          p.failed.push({ file: e.file ?? "", message: e.message });
        }
        setProgress({ ...p, failed: [...p.failed] });
      });
      await refresh(s);
    } catch (e) {
      setError(asError(e));
    } finally {
      setBusy(false);
      setProgress((cur) => (cur && cur.failed.length ? cur : null));
    }
  }, [api, refresh]);

  const openFolder = useCallback(async (source: string) => {
    try {
      const s = await api.openSource(source);
      setSession(s);
      setReview(null);
      setSelected(null);
      rememberFolder(source);
      // Mode demo tidak perlu memproses; mesin sungguhan melewati foto yang sudah selesai.
      if (api.mode === "demo") await refresh(s);
      else await runProcess(s);
    } catch (e) {
      setError(asError(e));
    }
  }, [api, refresh, runProcess]);

  const choose = async () => {
    try {
      const source = await api.chooseFolder();
      if (source) await openFolder(source);
    } catch (e) {
      setError(asError(e));
    }
  };

  // Folder dari baris perintah (atau mode demo) langsung dibuka.
  useEffect(() => {
    let live = true;
    api.startupFolder().then((f) => { if (live && f) void openFolder(f); }, () => undefined);
    return () => { live = false; };
  }, [api, openFolder]);

  const lastFolder = recallFolder();

  useEffect(() => {
    setField(null);
    setLine(null);
    setDetail(null);
    if (!session || !selected) return;
    let live = true;
    api.page(session, selected).then((d) => live && setDetail(d), (e) => live && setError(asError(e)));
    return () => { live = false; };
  }, [api, session, selected]);

  // J/K atau panah: pindah foto (kecuali sedang mengetik).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement;
      if (t.closest("input, textarea, select") || e.ctrlKey || e.metaKey || e.altKey) return;
      const dir = e.key === "j" || e.key === "ArrowDown" ? 1 : e.key === "k" || e.key === "ArrowUp" ? -1 : 0;
      if (!dir) return;
      e.preventDefault();
      setSelected((cur) => stepPage(shown, cur, dir));
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [shown]);

  const mutate = async (fn: () => Promise<void>, message: string) => {
    if (!session) return;
    await fn(); // galat dilempar ke form yang memanggil, ditampilkan di sana
    await refresh(session);
    say(message);
  };

  const actions: LedgerActions | null = session && page ? {
    correct: (f, value, reason) => mutate(() => api.correct(session, page.sha256, f.id, value, reason, f.value), "Koreksi disimpan"),
    addField: (kind, value, reason, fromLine) =>
      mutate(() => api.addField(session, page.sha256, kind, value, reason, fromLine), "Nilai ditambahkan"),
    confirm: () => mutate(() => api.confirm(session, page.sha256), "Foto dikonfirmasi"),
    unconfirm: (reason) => mutate(() => api.unconfirm(session, page.sha256, reason), "Konfirmasi dibatalkan"),
    next: () => setSelected(nextOpenPage(pages, page.sha256)),
  } : null;

  const runVerify = async () => {
    if (!session) return;
    setBusy(true);
    try {
      setVerify(await api.verify(session));
    } catch (e) {
      setError(asError(e));
    } finally {
      setBusy(false);
    }
  };

  const runExport = async () => {
    if (!session) return;
    setBusy(true);
    setError(null);
    setExported(null);
    try {
      setExported(await api.exportFiles(session));
      say("Excel diexport");
    } catch (e) {
      setError(asError(e));
    } finally {
      setBusy(false);
    }
  };

  const pct = progress && progress.total ? (progress.done / progress.total) * 100 : progress ? 2 : 0;

  return (
    <div className="app">
      <TopBar session={session} busy={busy} demo={api.mode === "demo"} onChoose={choose}
        onProcess={() => session && runProcess(session)} onVerify={runVerify} onExport={runExport} />
      <div className="progress" aria-hidden={!busy}>
        {busy && progress && <div style={{ width: `${pct}%` }} />}
      </div>
      <Banners error={error} verify={verify} exported={exported} progress={busy ? null : progress}
        onOpenOutput={session && api.mode === "desktop" ? () => { api.openOutput(session).catch((e) => setError(asError(e))); } : undefined}
        onClose={() => { setError(null); setVerify(null); setExported(null); setProgress(null); }} />
      {!session || !review ? (
        <main className="empty">
          {busy && progress ? (
            <>
              <h1>Membaca foto…</h1>
              <p className="mono">{progress.done} dari {progress.total || "?"} foto</p>
            </>
          ) : (
            <>
              <h1>Pilih folder foto vouching</h1>
              <p>Semua foto di folder itu (termasuk subfolder) dibaca dengan OCR di laptop ini. Lalu cek tiap nilai di samping fotonya.</p>
              <div className="row" style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
                <button className="btn btn-ink" onClick={choose}>Pilih folder</button>
                {lastFolder && (
                  <button className="link mono" onClick={() => openFolder(lastFolder)} title={lastFolder}>
                    Buka lagi: {lastFolder.split(/[\\/]/).pop()}
                  </button>
                )}
              </div>
              <p className="safe">Bisa foto (JPG, PNG, TIFF), PDF, dan Word (.docx). Folder klien hanya dibaca, tidak pernah diubah. Folder bernama Backup dilewati. Hasil OCR, jejak audit, dan Excel disimpan di folder Output OCR di folder program.</p>
            </>
          )}
        </main>
      ) : (
        <div className="panes">
          <PhotoList pages={pages} filter={filter} selected={selected} onFilter={setFilter} onSelect={setSelected} />
          {page && actions ? (
            <>
              <PhotoView page={page} detail={detail}
                imageUrl={page.image ? api.workspaceUrl(session, page.image) : api.imageUrl(session, page.files[0] ?? "")}
                selectedField={field} onSelectField={(id) => { setLine(null); setField(id); }}
                selectedLine={line} onSelectLine={(i) => { setField(null); setLine(i); }} />
              <Ledger page={page} detail={detail} selectedField={field}
                onSelectField={(id) => { setLine(null); setField(id); }}
                selectedLine={line} onSelectLine={(i) => { setField(null); setLine(i); }} actions={actions}
                hasNext={nextOpenPage(pages, page.sha256) !== null} />
            </>
          ) : (
            <main className="empty" style={{ gridColumn: "2 / 4" }}>
              <h1>Tidak ada foto</h1>
              <p>Folder ini tidak berisi foto, PDF, atau Word (.docx) di luar folder Backup.</p>
            </main>
          )}
        </div>
      )}
      {toast && <div className="toast" role="status">{toast}</div>}
    </div>
  );
}

// Folder terakhir hanya kenyamanan; kalau penyimpanan browser tidak tersedia, abaikan.
const LAST_KEY = "meja-vouching:last-folder";
function rememberFolder(path: string) {
  try { localStorage.setItem(LAST_KEY, path); } catch { /* tidak apa-apa */ }
}
function recallFolder(): string | null {
  try { return localStorage.getItem(LAST_KEY); } catch { return null; }
}

function Banners({ error, verify, exported, progress, onClose, onOpenOutput }: {
  error: ApiError | null; verify: VerifyResult | null; exported: ExportResult | null; progress: Progress | null;
  onClose: () => void; onOpenOutput?: () => void;
}) {
  if (!error && !verify && !exported && !progress?.failed.length) return null;
  return (
    <div style={{ display: "grid", gap: 6, paddingBottom: 8, borderBottom: "1px solid var(--paper-rule)" }}>
      {error && (
        <div className="note note-error" role="alert">
          {error.message}{error.hint && <span className="hint">{error.hint}</span>}
        </div>
      )}
      {progress && progress.failed.length > 0 && (
        <div className="note note-error" role="alert">
          {progress.failed.length} foto tidak bisa dibaca dan dilewati:
          {progress.failed.map((f) => <span key={f.file} className="hint mono">{f.file}: {f.message}</span>)}
        </div>
      )}
      {verify && (
        <div className={`note ${verify.ok ? "note-ok" : "note-error"}`} role="status">
          {verify.ok
            ? `Jejak audit utuh: ${verify.entries} catatan berantai, ${verify.pages_checked} hasil OCR cocok dengan hash-nya.`
            : "Jejak audit TIDAK utuh:"}
          {verify.problems.map((p) => <span key={p} className="hint">{p}</span>)}
        </div>
      )}
      {exported && (
        <div className="note note-ok" role="status">
          Excel diexport: {exported.pages} foto, {exported.confirmed} dikonfirmasi
          {exported.pages > exported.confirmed && ` (${exported.pages - exported.confirmed} belum dicek, ditandai di kolom Status)`}.
          Hash file dicatat di jejak audit.
          {exported.files.map((f) => <span key={f.path} className="hint mono">{f.path}</span>)}
          {onOpenOutput && <span className="hint"><button className="link" onClick={onOpenOutput}>Buka folder hasil</button></span>}
        </div>
      )}
      <div style={{ padding: "0 18px" }}><button className="link" onClick={onClose}>Tutup pesan</button></div>
    </div>
  );
}
