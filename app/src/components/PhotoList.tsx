import type { PageState } from "../api/types";
import { baseName, dirName } from "../lib/paths";
import { FILTER_LABEL, filterPages, hasDoubt, type PageFilter, summarize } from "../lib/review";
import { Tick } from "./icons";

interface Props {
  pages: PageState[];
  filter: PageFilter;
  selected: string | null;
  onFilter: (f: PageFilter) => void;
  onSelect: (sha: string) => void;
}

export function PhotoList({ pages, filter, selected, onFilter, onSelect }: Props) {
  const shown = filterPages(pages, filter);
  const s = summarize(pages);
  return (
    <nav className="pane" aria-label="Daftar foto">
      <div className="filters" role="group" aria-label="Saring foto">
        {(Object.keys(FILTER_LABEL) as PageFilter[]).map((f) => (
          <button key={f} className="filter" aria-pressed={filter === f} onClick={() => onFilter(f)}>
            {FILTER_LABEL[f]}
            <span className="count">{filterPages(pages, f).length}</span>
          </button>
        ))}
      </div>
      <div className="tally">{s.confirmed} dari {s.total} foto dikonfirmasi</div>
      <ul className="photo-list">
        {shown.map((p) => {
          const file = p.files[0] ?? p.sha256;
          const folder = dirName(file);
          return (
            <li key={p.sha256}>
              <button className="photo-item" aria-current={p.sha256 === selected} onClick={() => onSelect(p.sha256)}>
                <span className="name">
                  {baseName(file)}
                  {(folder || p.files.length > 1) && (
                    <span className="folder">
                      {folder}
                      {p.files.length > 1 && `${folder ? " · " : ""}${p.files.length} file identik`}
                    </span>
                  )}
                </span>
                <StatusMark page={p} />
              </button>
            </li>
          );
        })}
        {shown.length === 0 && <li className="tally" style={{ paddingTop: 12 }}>Tidak ada foto di saringan ini.</li>}
      </ul>
      <div className="list-foot"><kbd>J</kbd> <kbd>K</kbd> pindah foto</div>
    </nav>
  );
}

function StatusMark({ page }: { page: PageState }) {
  if (page.status === "dikonfirmasi") return <span className="status-mark" title="Dikonfirmasi"><Tick /></span>;
  if (hasDoubt(page)) return <span className="status-mark" title="Ada keraguan"><span className="status-doubt" /></span>;
  return <span className="status-mark" title="Belum dicek"><span className="status-open" /></span>;
}
