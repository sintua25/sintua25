import type { Session } from "../api/types";
import { ChainIcon, FolderIcon, ScanIcon } from "./icons";

interface Props {
  session: Session | null;
  busy: boolean;
  demo: boolean;
  onChoose: () => void;
  onProcess: () => void;
  onVerify: () => void;
}

export function TopBar({ session, busy, demo, onChoose, onProcess, onVerify }: Props) {
  return (
    <header className="topbar">
      <div className="wordmark">Meja Vouching<span>.</span></div>
      <div className="source-path mono" title={session ? `Folder kerja: ${session.workspace}` : undefined}>
        {session ? session.source : "Belum ada folder dipilih"}
        {demo && " · mode demo"}
      </div>
      <button className="btn" onClick={onChoose} disabled={busy}><FolderIcon />Pilih folder</button>
      <button className="btn" onClick={onProcess} disabled={busy || !session}><ScanIcon />Proses foto</button>
      <button className="btn" onClick={onVerify} disabled={busy || !session}><ChainIcon />Periksa jejak audit</button>
    </header>
  );
}
