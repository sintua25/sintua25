mod engine;

use engine::{workspace_name, ApiError, Engine};
use serde::Serialize;
use serde_json::Value;
use std::path::PathBuf;
use tauri::{ipc::Channel, AppHandle, Manager};

#[derive(Serialize)]
struct Session {
    source: String,
    workspace: String,
}

/// Jalankan pekerjaan mesin di thread terpisah supaya jendela tidak beku.
async fn blocking<T: Send + 'static>(
    f: impl FnOnce() -> Result<T, ApiError> + Send + 'static,
) -> Result<T, ApiError> {
    tauri::async_runtime::spawn_blocking(f)
        .await
        .map_err(|e| ApiError::new("INTERNAL", format!("Tugas latar gagal: {e}"), "Coba lagi."))?
}

fn call(args: Vec<String>) -> impl FnOnce() -> Result<Value, ApiError> + Send + 'static {
    move || {
        let refs: Vec<&str> = args.iter().map(String::as_str).collect();
        Engine::locate().call(&refs)
    }
}

/// `--nama=nilai` dalam satu argumen: nilai yang diawali "-" (nominal negatif, alasan
/// berawalan tanda hubung) tidak salah dibaca sebagai opsi oleh argparse.
fn opt(name: &str, value: &str) -> String {
    format!("--{name}={value}")
}

/// Folder sumber dipilih: tentukan folder kerja (di Dokumen, di luar folder klien)
/// dan izinkan foto di folder sumber tampil lewat asset protocol.
#[tauri::command]
async fn open_source(app: AppHandle, source: String) -> Result<Session, ApiError> {
    let src = PathBuf::from(&source);
    if !src.is_dir() {
        return Err(ApiError::new("SOURCE_MISSING", format!("Folder '{source}' tidak ada."), "Pilih ulang folder foto."));
    }
    // Dokumen kalau ada (Windows selalu punya); kalau tidak, folder data aplikasi.
    let docs = app.path().document_dir().or_else(|_| app.path().app_data_dir()).map_err(|e| {
        ApiError::new("NO_WORKSPACE_DIR", format!("Tidak ada tempat menyimpan folder kerja: {e}"),
            "Pastikan akun komputer ini punya folder Dokumen yang bisa ditulisi.")
    })?;
    let workspace = docs.join("Meja Vouching").join(workspace_name(&src));
    app.asset_protocol_scope().allow_directory(&src, true).map_err(|e| {
        ApiError::new("ASSET_SCOPE", format!("Foto di folder ini tidak bisa ditampilkan: {e}"), "Pilih ulang folder.")
    })?;
    Ok(Session { source, workspace: workspace.to_string_lossy().into_owned() })
}

/// Folder yang diberikan saat aplikasi dibuka (`meja-vouching.exe "C:\\Klien\\Kas"`,
/// atau folder yang di-drop ke ikon aplikasi). Hanya kalau memang folder.
#[tauri::command]
fn startup_source() -> Option<String> {
    std::env::args_os().skip(1).map(PathBuf::from).find(|p| p.is_dir()).map(|p| p.to_string_lossy().into_owned())
}

#[tauri::command]
async fn process(source: String, workspace: String, on_event: Channel<Value>) -> Result<(), ApiError> {
    blocking(move || {
        let ws = opt("workspace", &workspace);
        // Path folder sumber adalah argumen posisi; "--" mencegahnya dibaca sebagai opsi.
        Engine::locate().stream(&["process", &ws, "--", &source], |event| {
            let _ = on_event.send(event); // jendela ditutup di tengah proses: abaikan
        })
    })
    .await
}

#[tauri::command]
async fn review_state(workspace: String) -> Result<Value, ApiError> {
    blocking(call(vec!["state".into(), "-w".into(), workspace])).await
}

#[tauri::command]
async fn page_detail(workspace: String, sha: String) -> Result<Value, ApiError> {
    blocking(call(vec!["page".into(), "-w".into(), workspace, "--page".into(), sha])).await
}

#[tauri::command]
async fn correct(
    workspace: String,
    sha: String,
    field: u32,
    value: String,
    reason: String,
    expected: String,
) -> Result<Value, ApiError> {
    blocking(call(vec![
        "correct".into(), "-w".into(), workspace, "--page".into(), sha, "--field".into(), field.to_string(),
        opt("value", &value), opt("reason", &reason), opt("expected", &expected),
    ]))
    .await
}

#[tauri::command]
async fn add_field(workspace: String, sha: String, kind: String, value: String, reason: String) -> Result<Value, ApiError> {
    blocking(call(vec![
        "add-field".into(), "-w".into(), workspace, "--page".into(), sha, opt("kind", &kind),
        opt("value", &value), opt("reason", &reason),
    ]))
    .await
}

#[tauri::command]
async fn confirm(workspace: String, sha: String) -> Result<Value, ApiError> {
    blocking(call(vec!["confirm".into(), "-w".into(), workspace, "--page".into(), sha])).await
}

#[tauri::command]
async fn unconfirm(workspace: String, sha: String, reason: String) -> Result<Value, ApiError> {
    blocking(call(vec!["unconfirm".into(), "-w".into(), workspace, "--page".into(), sha, opt("reason", &reason)])).await
}

#[tauri::command]
async fn verify(workspace: String) -> Result<Value, ApiError> {
    blocking(call(vec!["verify".into(), "-w".into(), workspace])).await
}

/// Excel + JSON ke `<folder kerja>/export`; mesin mencatat hash-nya di jejak audit.
#[tauri::command]
async fn export_files(workspace: String) -> Result<Value, ApiError> {
    blocking(call(vec!["export".into(), "-w".into(), workspace])).await
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .invoke_handler(tauri::generate_handler![
            startup_source, open_source, process, review_state, page_detail, correct, add_field, confirm, unconfirm, verify, export_files
        ])
        .run(tauri::generate_context!())
        .expect("gagal menjalankan Meja Vouching");
}
