import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import type { Api } from "./api/api";
import { tauriApi } from "./api/tauri";
import "./styles.css";

// Di jendela Tauri pakai mesin sungguhan; di browser biasa pakai data demo (dimuat terpisah).
const api: Api = "__TAURI_INTERNALS__" in window ? tauriApi : (await import("./api/demo")).createDemoApi();

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App api={api} />
  </StrictMode>,
);
