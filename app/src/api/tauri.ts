import { Channel, convertFileSrc, invoke } from "@tauri-apps/api/core";
import { open } from "@tauri-apps/plugin-dialog";
import type { Api } from "./api";
import type { ExportResult, PageDetail, ProcessEvent, ReviewState, Session, VerifyResult } from "./types";
import { joinPath } from "../lib/paths";

export const tauriApi: Api = {
  mode: "desktop",

  async chooseFolder() {
    const picked = await open({ directory: true, multiple: false, title: "Pilih folder foto vouching" });
    return typeof picked === "string" ? picked : null;
  },

  startupFolder: () => invoke<string | null>("startup_source"),

  openSource: (source) => invoke<Session>("open_source", { source }),

  async process(session, onEvent) {
    const channel = new Channel<ProcessEvent>();
    channel.onmessage = onEvent;
    await invoke("process", { source: session.source, workspace: session.workspace, onEvent: channel });
  },

  state: (s) => invoke<ReviewState>("review_state", { workspace: s.workspace }),
  page: (s, sha) => invoke<PageDetail>("page_detail", { workspace: s.workspace, sha }),
  imageUrl: (s, rel) => convertFileSrc(joinPath(s.source, rel)),
  workspaceUrl: (s, rel) => convertFileSrc(joinPath(s.workspace, rel)),

  async correct(s, sha, field, value, reason, expected) {
    await invoke("correct", { workspace: s.workspace, sha, field, value, reason, expected });
  },
  async addField(s, sha, kind, value, reason, line) {
    await invoke("add_field", { workspace: s.workspace, sha, kind, value, reason, line: line ?? null });
  },
  async confirm(s, sha) {
    await invoke("confirm", { workspace: s.workspace, sha });
  },
  async unconfirm(s, sha, reason) {
    await invoke("unconfirm", { workspace: s.workspace, sha, reason });
  },
  verify: (s) => invoke<VerifyResult>("verify", { workspace: s.workspace }),
  exportFiles: (s) => invoke<ExportResult>("export_files", { workspace: s.workspace }),
};
