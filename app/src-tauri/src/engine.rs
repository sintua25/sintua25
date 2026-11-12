//! Menjalankan mesin OCR Python (`python -m vouchocr`) dan membaca JSON Lines-nya.
//!
//! Mesin adalah satu-satunya yang menulis hasil OCR dan jejak audit; aplikasi ini
//! hanya meneruskan perintah dan galatnya, supaya aturan audit ada di satu tempat.

use serde::Serialize;
use serde_json::Value;
use std::io::{BufRead, BufReader, Read};
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};

/// Galat yang dikirim ke UI: apa yang terjadi + apa yang bisa dilakukan pengguna.
#[derive(Debug, Clone, Serialize, PartialEq)]
pub struct ApiError {
    pub code: String,
    pub message: String,
    pub hint: String,
}

impl ApiError {
    pub fn new(code: &str, message: impl Into<String>, hint: impl Into<String>) -> Self {
        Self { code: code.into(), message: message.into(), hint: hint.into() }
    }
}

const INSTALL_HINT: &str = "Pasang mesin OCR sekali saja: buka folder engine, jalankan \
`python -m venv .venv` lalu `.venv\\Scripts\\pip install -e .`. \
Atau isi variabel VOUCHOCR_PYTHON dengan lokasi python yang sudah berisi vouchocr.";

pub struct Engine {
    python: PathBuf,
}

impl Engine {
    /// Urutan: VOUCHOCR_PYTHON, venv engine di repo (mode pengembangan), python di PATH.
    pub fn locate() -> Self {
        if let Some(p) = std::env::var_os("VOUCHOCR_PYTHON") {
            return Self { python: PathBuf::from(p) };
        }
        let repo_venv = Path::new(env!("CARGO_MANIFEST_DIR")).join("..").join("..").join("engine").join(".venv");
        let candidate = if cfg!(windows) {
            repo_venv.join("Scripts").join("python.exe")
        } else {
            repo_venv.join("bin").join("python")
        };
        if candidate.exists() {
            return Self { python: candidate };
        }
        Self { python: PathBuf::from(if cfg!(windows) { "python" } else { "python3" }) }
    }

    fn command(&self, args: &[&str]) -> Command {
        let mut cmd = Command::new(&self.python);
        cmd.arg("-m").arg("vouchocr").args(args);
        // JSON dari Python selalu UTF-8, termasuk nama file berhuruf non-ASCII di Windows.
        cmd.env("PYTHONUTF8", "1").env("PYTHONIOENCODING", "utf-8");
        cmd.stdin(Stdio::null()).stdout(Stdio::piped()).stderr(Stdio::piped());
        #[cfg(windows)]
        {
            use std::os::windows::process::CommandExt;
            const CREATE_NO_WINDOW: u32 = 0x0800_0000;
            cmd.creation_flags(CREATE_NO_WINDOW);
        }
        cmd
    }

    fn spawn_error(&self, e: std::io::Error) -> ApiError {
        if e.kind() == std::io::ErrorKind::NotFound {
            ApiError::new("ENGINE_MISSING", format!("Python tidak ditemukan ({}).", self.python.display()), INSTALL_HINT)
        } else {
            ApiError::new("ENGINE_START_FAILED", format!("Mesin OCR gagal dijalankan: {e}."), INSTALL_HINT)
        }
    }

    /// Jalankan satu perintah dan kembalikan objek JSON terakhir.
    pub fn call(&self, args: &[&str]) -> Result<Value, ApiError> {
        let out = self.command(args).output().map_err(|e| self.spawn_error(e))?;
        interpret(&String::from_utf8_lossy(&out.stdout), &String::from_utf8_lossy(&out.stderr), out.status.success())
    }

    /// Jalankan perintah panjang; setiap baris JSON diteruskan begitu muncul (untuk progres).
    pub fn stream(&self, args: &[&str], mut on_event: impl FnMut(Value)) -> Result<(), ApiError> {
        let mut child = self.command(args).spawn().map_err(|e| self.spawn_error(e))?;
        let mut stderr = child.stderr.take().expect("stderr dipipe");
        // stderr dibaca di thread lain supaya pipa tidak penuh dan proses tidak macet.
        let err_reader = std::thread::spawn(move || {
            let mut s = String::new();
            let _ = stderr.read_to_string(&mut s);
            s
        });
        let mut last: Option<Value> = None;
        for line in BufReader::new(child.stdout.take().expect("stdout dipipe")).lines() {
            let Ok(line) = line else { break };
            if let Ok(v) = serde_json::from_str::<Value>(&line) {
                on_event(v.clone());
                last = Some(v);
            }
        }
        let status = child.wait().map_err(|e| self.spawn_error(e))?;
        let stderr = err_reader.join().unwrap_or_default();
        match (status.success(), last) {
            (true, _) => Ok(()),
            (false, Some(v)) if v.get("type").and_then(Value::as_str) == Some("error") => Err(to_api_error(&v)),
            (false, _) => Err(crashed(&stderr)),
        }
    }
}

/// Tafsirkan keluaran satu perintah. Terpisah supaya bisa dites tanpa Python.
pub fn interpret(stdout: &str, stderr: &str, success: bool) -> Result<Value, ApiError> {
    let last = stdout.lines().rev().find_map(|l| serde_json::from_str::<Value>(l).ok());
    match last {
        Some(v) if v.get("type").and_then(Value::as_str) == Some("error") => Err(to_api_error(&v)),
        // `verify` keluar dengan kode 1 saat rantai rusak, tapi itu hasil, bukan galat.
        Some(v) => Ok(v),
        None if success => Err(ApiError::new("ENGINE_NO_OUTPUT", "Mesin OCR tidak mengirim hasil.", "Coba lagi.")),
        None => Err(crashed(stderr)),
    }
}

fn to_api_error(v: &Value) -> ApiError {
    let s = |k: &str| v.get(k).and_then(Value::as_str).unwrap_or_default().to_string();
    ApiError { code: s("code"), message: s("message"), hint: s("hint") }
}

fn crashed(stderr: &str) -> ApiError {
    if stderr.contains("No module named vouchocr") {
        return ApiError::new("ENGINE_MISSING", "Python ada, tapi mesin OCR (vouchocr) belum terpasang.", INSTALL_HINT);
    }
    let tail: Vec<&str> = stderr.lines().rev().take(6).collect::<Vec<_>>().into_iter().rev().collect();
    ApiError::new(
        "ENGINE_CRASHED",
        format!("Mesin OCR berhenti tidak normal. {}", tail.join(" | ")),
        "Foto yang sudah selesai tetap tersimpan. Jalankan lagi; kalau terulang, kirim pesan ini ke pengembang.",
    )
}

/// Nama folder kerja: nama folder sumber + sidik 8 heksa dari path lengkapnya,
/// supaya dua folder bernama sama di tempat berbeda tidak tercampur.
pub fn workspace_name(source: &Path) -> String {
    // Dipisah manual (bukan Path::file_name) supaya path Windows juga benar saat dites di Linux.
    let normalized = source.to_string_lossy().replace('\\', "/");
    let trimmed = normalized.trim_end_matches('/');
    let name: String = trimmed
        .rsplit('/')
        .next()
        .filter(|n| !n.is_empty())
        .unwrap_or("folder")
        .chars()
        .map(|c| if "<>:\"/\\|?*".contains(c) || c.is_control() { '_' } else { c })
        .collect();
    let key = trimmed.to_lowercase();
    // FNV-1a 64-bit: stabil antar versi Rust (DefaultHasher tidak dijamin stabil).
    let mut h: u64 = 0xcbf2_9ce4_8422_2325;
    for b in key.bytes() {
        h ^= u64::from(b);
        h = h.wrapping_mul(0x0100_0000_01b3);
    }
    format!("{} - {:08x}", name.trim(), h >> 32)
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn last_json_line_wins() {
        let v = interpret("noise\n{\"type\":\"saved\",\"n\":1}\n{\"type\":\"saved\",\"n\":2}\n", "", true).unwrap();
        assert_eq!(v["n"], 2);
    }

    #[test]
    fn engine_error_is_passed_through() {
        let out = json!({"type":"error","code":"REASON_REQUIRED","message":"Alasan wajib diisi.","hint":"Tulis alasan."});
        let e = interpret(&out.to_string(), "", false).unwrap_err();
        assert_eq!(e, ApiError::new("REASON_REQUIRED", "Alasan wajib diisi.", "Tulis alasan."));
    }

    #[test]
    fn verify_failure_is_a_result_not_an_error() {
        let v = interpret(r#"{"type":"verify","ok":false,"problems":["x"]}"#, "", false).unwrap();
        assert_eq!(v["ok"], false);
    }

    #[test]
    fn missing_module_explained() {
        let e = interpret("", "C:\\py\\python.exe: No module named vouchocr", false).unwrap_err();
        assert_eq!(e.code, "ENGINE_MISSING");
        assert!(e.hint.contains("pip install"));
    }

    #[test]
    fn crash_keeps_stderr_tail() {
        let e = interpret("", "Traceback\n  File x\nValueError: rusak", false).unwrap_err();
        assert_eq!(e.code, "ENGINE_CRASHED");
        assert!(e.message.contains("ValueError: rusak"));
    }

    #[test]
    fn empty_success_is_not_silent() {
        assert_eq!(interpret("", "", true).unwrap_err().code, "ENGINE_NO_OUTPUT");
    }

    #[test]
    fn workspace_name_is_stable_and_distinct() {
        let a = workspace_name(Path::new("C:\\Klien A\\Kas Maret"));
        let a2 = workspace_name(Path::new("c:/klien a/kas maret/"));
        let b = workspace_name(Path::new("C:\\Klien B\\Kas Maret"));
        assert!(a.starts_with("Kas Maret - "));
        assert_eq!(a.len(), "Kas Maret - ".len() + 8);
        assert_eq!(&a[12..], &a2[12..], "beda huruf besar/kecil dan garis miring = folder yang sama");
        assert_ne!(a, b);
    }

    /// Alur penuh lewat jembatan Rust -> Python sungguhan. Jalan hanya kalau
    /// VOUCHOCR_TEST_FOLDER (folder foto contoh) dan VOUCHOCR_PYTHON diisi.
    #[test]
    fn bridge_end_to_end_with_real_engine() {
        let Some(folder) = std::env::var_os("VOUCHOCR_TEST_FOLDER") else { return };
        let ws = std::env::temp_dir().join(format!("mv-bridge-{}", std::process::id()));
        let ws_opt = format!("--workspace={}", ws.display());
        let engine = Engine::locate();

        let mut types = vec![];
        engine.stream(&["process", &ws_opt, "--", folder.to_str().unwrap()], |v| {
            types.push(v["type"].as_str().unwrap_or_default().to_string());
        }).unwrap();
        assert_eq!(types.first().map(String::as_str), Some("start"));
        assert_eq!(types.last().map(String::as_str), Some("done"));

        let state = engine.call(&["state", &ws_opt]).unwrap();
        let page = &state["pages"][0];
        let sha = page["sha256"].as_str().unwrap();
        let amount = page["fields"].as_array().unwrap().iter().find(|f| f["kind"] == "amount").unwrap();
        let id = amount["id"].to_string();
        let expected = format!("--expected={}", amount["value"].as_str().unwrap());

        // Nominal negatif dan alasan berawalan "-" tidak boleh dibaca sebagai opsi.
        let saved = engine.call(&["correct", &ws_opt, "--page", sha, "--field", &id, "--value=-500", "--reason=-nota kredit", &expected]).unwrap();
        assert_eq!(saved["entry"]["after"], "-500");
        let err = engine.call(&["correct", &ws_opt, "--page", sha, "--field", &id, "--value=1", "--reason="]).unwrap_err();
        assert_eq!(err.code, "REASON_REQUIRED");
        engine.call(&["confirm", &ws_opt, "--page", sha]).unwrap();

        let v = engine.call(&["verify", &ws_opt]).unwrap();
        assert_eq!(v["ok"], true, "{v}");
        std::fs::write(ws.join("audit.jsonl"), "{}\n").unwrap();
        let v = engine.call(&["verify", &ws_opt]).unwrap();
        assert_eq!(v["ok"], false);
        let _ = std::fs::remove_dir_all(&ws);
    }

    #[test]
    fn workspace_name_sanitized() {
        assert_eq!(&workspace_name(Path::new("/x/a:b?c"))[..5], "a_b_c");
    }
}
