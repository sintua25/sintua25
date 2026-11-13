/**
 * @name StereoVoice
 * @author Alexander
 * @description Kirim suara mic dalam stereo (Opus 2 kanal) dengan bitrate yang bisa diatur. Matikan echo cancellation, noise suppression, dan AGC secara opsional.
 * @version 1.1.1
 */

/*
 * CATATAN UNTUK PENGEMBANG (handoff ke Claude Code)
 * -------------------------------------------------
 * Cara kerja:
 *   1. Ambil MediaEngineStore -> getMediaEngine() -> engine.connections.
 *   2. Patch `setTransportOptions` pada koneksi suara (prototype jika ada, kalau tidak instance).
 *   3. Sebelum opsi dikirim ke native voice engine, ubah:
 *        audioEncoder.channels = 2, audioEncoder.params.stereo = "1",
 *        audioEncoder.rate dan encodingVoiceBitRate = bitrate (bps).
 *   4. Opsional: matikan echo cancellation / noise suppression / AGC lewat action module
 *      Discord, lalu kembalikan nilai awalnya saat plugin dimatikan.
 *
 * Bagian yang bergantung pada internal Discord (paling mungkin berubah setelah update):
 *   - nama store "MediaEngineStore" dan method getMediaEngine()
 *   - properti engine.connections
 *   - nama method setTransportOptions dan bentuk objek opsinya
 *   - action setEchoCancellation / setNoiseSuppression / setAutomaticGainControl
 *
 * Debugging:
 *   - Aktifkan "Debug log" di pengaturan plugin, lalu lihat console (Ctrl+Shift+I).
 *   - Jalankan di console: BdApi.Plugins.get("StereoVoice").instance.diagnose()
 *   - Setiap panggilan setTransportOptions dicatat (kunci opsi sebelum dan sesudah diubah).
 *
 * Plugin ini sengaja tidak mengubah opsi jika audioEncoder tidak ada di panggilan tersebut,
 * supaya tidak merusak update parsial yang dikirim Discord (mute, dll).
 * Setelah plugin diaktifkan, pengguna harus keluar lalu masuk lagi ke voice channel.
 *
 * Perubahan 1.1.0:
 *   - Koneksi baru dipatch saat itu juga (hook pada engine.connections.add dan pada
 *     prototype wrapper koneksi yang punya updateVideoQuality). Sebelumnya patch hanya
 *     dipasang tiap 2 detik, jadi panggilan pertama setTransportOptions yang membawa
 *     audioEncoder (tepat saat join) sering lolos tanpa diubah. Polling 2 detik tetap ada
 *     sebagai fallback.
 *   - reapply() sekarang memakai opsi ASLI dari Discord lalu ditransformasi ulang.
 *     Sebelumnya opsi yang sudah diubah disimpan, jadi mematikan Stereo tetap kirim 2 kanal.
 *   - Action echo/noise/AGC dicari juga lewat nama action dispatch (modul Discord sekarang
 *     sering diekspor dengan nama acak/minified).
 *   - diagnose() melaporkan lebih banyak detail (bentuk koneksi, opsi terakhir).
 *
 * Perubahan 1.1.1 (dari diagnose() di Discord asli, 2026-11-13):
 *   - Bentuk terkonfirmasi: engine.connections = Set berisi wrapper (punya setCodecs,
 *     setVoiceBitRate, voiceBitrate) dengan .conn = Object biasa yang punya
 *     setTransportOptions sebagai properti sendiri (patch instance).
 *   - Update parsial yang hanya membawa encodingVoiceBitRate sekarang ikut diganti nilainya,
 *     supaya setVoiceBitRate Discord tidak mengembalikan bitrate ke bawaan channel.
 *   - Hook tambahan sebelum wrapper.setCodecs.
 */

module.exports = class StereoVoice {
  constructor(meta) {
    this.meta = meta || {};
    this.id = this.meta.name || "StereoVoice";
    this.defaults = {
      stereo: true,
      bitrate: 256, // kbps
      disableProcessing: true,
      restoreProcessing: true,
      debug: false,
    };
    this.settings = this.loadSettings();
    this.patchedTargets = new WeakSet();
    this.lastOptions = new WeakMap(); // koneksi -> opsi ASLI terakhir yang memuat audioEncoder
    this.savedProcessing = null;
    this.timer = null;
    this.hooks = { connectionsAdd: false, wrapperPrototype: false };
    this.lastSeen = null; // ringkasan panggilan setTransportOptions terakhir (untuk diagnose)
  }

  /* ---------- util ---------- */

  log(...args) {
    try {
      BdApi.Logger.info(this.id, ...args);
    } catch (e) {
      console.log(`[${this.id}]`, ...args);
    }
  }

  warn(...args) {
    try {
      BdApi.Logger.warn(this.id, ...args);
    } catch (e) {
      console.warn(`[${this.id}]`, ...args);
    }
  }

  debug(...args) {
    if (this.settings.debug) this.log(...args);
  }

  loadSettings() {
    let saved = {};
    try {
      saved = BdApi.Data.load(this.id, "settings") || {};
    } catch (e) {
      saved = {};
    }
    const merged = { ...this.defaults, ...saved };
    merged.bitrate = this.clampBitrate(merged.bitrate);
    return merged;
  }

  clampBitrate(v) {
    return Math.min(510, Math.max(8, Number(v) || this.defaults.bitrate));
  }

  saveSettings() {
    try {
      BdApi.Data.save(this.id, "settings", this.settings);
    } catch (e) {
      this.warn("Gagal menyimpan pengaturan:", e);
    }
  }

  toast(message, type = "info") {
    try {
      BdApi.UI.showToast(message, { type });
    } catch (e) {
      /* abaikan */
    }
  }

  /* ---------- akses internal Discord ---------- */

  getStore() {
    try {
      if (BdApi.Webpack.getStore) {
        const s = BdApi.Webpack.getStore("MediaEngineStore");
        if (s) return s;
      }
    } catch (e) {
      /* lanjut ke fallback */
    }
    try {
      return BdApi.Webpack.getModule(
        (m) => m && typeof m.getName === "function" && m.getName() === "MediaEngineStore" && typeof m.getMediaEngine === "function"
      );
    } catch (e) {
      return null;
    }
  }

  getEngine() {
    try {
      const store = this.getStore();
      return store && typeof store.getMediaEngine === "function" ? store.getMediaEngine() : null;
    } catch (e) {
      return null;
    }
  }

  getConnections() {
    const engine = this.getEngine();
    const raw = engine && engine.connections;
    if (!raw) return [];
    try {
      return Array.from(raw);
    } catch (e) {
      return [];
    }
  }

  resolveConnection(candidate) {
    if (!candidate) return null;
    const options = [candidate, candidate.conn, candidate.connection, candidate.voiceConnection];
    for (const o of options) {
      if (o && typeof o.setTransportOptions === "function") return o;
    }
    return null;
  }

  getProcessingActions() {
    // 1) Cara lama: modul dengan nama method asli.
    try {
      const m = BdApi.Webpack.getModule(
        (m) => m && typeof m.setEchoCancellation === "function" && typeof m.setNoiseSuppression === "function"
      );
      if (m) return m;
    } catch (e) {
      /* lanjut */
    }
    // 2) Modul ter-minify: cari fungsi lewat nama action dispatch-nya.
    try {
      const W = BdApi.Webpack;
      if (typeof W.getMangled !== "function" || !W.Filters || typeof W.Filters.byStrings !== "function") return null;
      const m = W.getMangled(
        (mod) => {
          const fns = mod && typeof mod === "object" ? Object.values(mod).filter((v) => typeof v === "function") : [];
          const src = fns.map((f) => String(f)).join("\n");
          return src.includes("AUDIO_SET_ECHO_CANCELLATION") && src.includes("AUDIO_SET_NOISE_SUPPRESSION");
        },
        {
          setEchoCancellation: W.Filters.byStrings("AUDIO_SET_ECHO_CANCELLATION"),
          setNoiseSuppression: W.Filters.byStrings("AUDIO_SET_NOISE_SUPPRESSION"),
          setAutomaticGainControl: W.Filters.byStrings("AUDIO_SET_AUTOMATIC_GAIN_CONTROL"),
        }
      );
      if (m && typeof m.setEchoCancellation === "function" && typeof m.setNoiseSuppression === "function") return m;
    } catch (e) {
      /* tidak ketemu */
    }
    return null;
  }

  getWrapperPrototype() {
    try {
      const W = BdApi.Webpack;
      if (!W.Filters || typeof W.Filters.byPrototypeKeys !== "function") return null;
      const cls = W.getModule(W.Filters.byPrototypeKeys("updateVideoQuality"), { searchExports: true });
      return cls && cls.prototype ? cls.prototype : null;
    } catch (e) {
      return null;
    }
  }

  /* ---------- transformasi opsi ---------- */

  transform(opts) {
    if (!opts || typeof opts !== "object") return opts;
    const bps = Math.round(this.settings.bitrate * 1000);

    // Update parsial yang HANYA membawa bitrate (dari setVoiceBitRate / bitrate channel):
    // ganti nilainya saja, bentuk objek tetap. Tanpa ini Discord menimpa bitrate kita.
    if (!opts.audioEncoder || typeof opts.audioEncoder !== "object") {
      if (typeof opts.encodingVoiceBitRate === "number" && opts.encodingVoiceBitRate !== bps) {
        return { ...opts, encodingVoiceBitRate: bps };
      }
      return opts;
    }

    const out = { ...opts };
    const enc = { ...opts.audioEncoder };

    if (this.settings.stereo) {
      enc.channels = 2;
      enc.params = { ...(enc.params || {}), stereo: "1" };
    }
    enc.rate = bps;

    out.audioEncoder = enc;
    out.encodingVoiceBitRate = bps;
    return out;
  }

  /* ---------- patch koneksi ---------- */

  patchConnection(conn) {
    if (!conn || typeof conn.setTransportOptions !== "function") return false;

    const proto = Object.getPrototypeOf(conn);
    const target =
      proto && proto !== Object.prototype && Object.prototype.hasOwnProperty.call(proto, "setTransportOptions") ? proto : conn;

    if (this.patchedTargets.has(target)) return false;

    try {
      BdApi.Patcher.before(this.id, target, "setTransportOptions", (thisObj, args) => {
        try {
          const before = args[0];
          const after = this.transform(before);
          args[0] = after;
          // simpan opsi ASLI yang memuat audioEncoder; update parsial (mute, dll) jangan menimpa
          if (before && typeof before === "object" && before.audioEncoder) this.lastOptions.set(thisObj, before);
          this.lastSeen = {
            keysBefore: before && typeof before === "object" ? Object.keys(before) : typeof before,
            touched: before !== after,
            audioEncoder: after && after.audioEncoder,
            encodingVoiceBitRate: after && after.encodingVoiceBitRate,
          };
          if (this.settings.debug) this.log("setTransportOptions", this.lastSeen);
        } catch (e) {
          this.warn("Gagal mengubah opsi transport (opsi asli tetap dikirim):", e);
        }
      });
      this.patchedTargets.add(target);
      this.log(target === proto ? "Patch dipasang pada prototype koneksi." : "Patch dipasang pada instance koneksi.");
      return true;
    } catch (e) {
      this.warn("Gagal memasang patch:", e);
      return false;
    }
  }

  /** Pasang hook supaya koneksi baru langsung dipatch sebelum Discord mengirim opsi pertama. */
  installHooks() {
    // Hook A: engine.connections.add (Set/array koneksi aktif).
    const engine = this.getEngine();
    const set = engine && engine.connections;
    if (!this.hooks.connectionsAdd && set && typeof set.add === "function") {
      try {
        BdApi.Patcher.after(this.id, set, "add", (_set, args) => {
          this.debug("Koneksi baru ditambahkan, langsung dipatch.");
          this.patchConnection(this.resolveConnection(args[0]));
        });
        this.hooks.connectionsAdd = true;
      } catch (e) {
        this.debug("Hook connections.add gagal:", e);
      }
    }

    // Hook B: wrapper koneksi (class dengan updateVideoQuality, punya .conn native).
    // Cara ini dipakai beberapa plugin stereo publik.
    if (!this.hooks.wrapperPrototype) {
      const proto = this.getWrapperPrototype();
      if (proto) {
        try {
          BdApi.Patcher.after(this.id, proto, "updateVideoQuality", (thisObj) => {
            this.patchConnection(this.resolveConnection(thisObj));
          });
          // setCodecs adalah tempat Discord membangun audioEncoder; pastikan .conn sudah dipatch dulu.
          if (typeof proto.setCodecs === "function") {
            BdApi.Patcher.before(this.id, proto, "setCodecs", (thisObj) => {
              this.patchConnection(this.resolveConnection(thisObj));
            });
          }
          this.hooks.wrapperPrototype = true;
        } catch (e) {
          this.debug("Hook updateVideoQuality gagal:", e);
        }
      }
    }
  }

  detect() {
    const engine = this.getEngine();
    if (!engine) return;
    this.installHooks();
    for (const candidate of this.getConnections()) {
      this.patchConnection(this.resolveConnection(candidate));
    }
  }

  reapply() {
    for (const candidate of this.getConnections()) {
      const conn = this.resolveConnection(candidate);
      if (!conn) continue;
      const last = this.lastOptions.get(conn) || this.lastOptions.get(candidate);
      if (!last) continue;
      try {
        // opsi asli dikirim lagi; patch akan mentransformasi dengan pengaturan terbaru
        conn.setTransportOptions(last);
        this.debug("Opsi diterapkan ulang ke koneksi aktif.");
      } catch (e) {
        this.warn("Gagal menerapkan ulang opsi:", e);
      }
    }
  }

  /* ---------- pemrosesan mic ---------- */

  applyProcessing() {
    const actions = this.getProcessingActions();
    const store = this.getStore();
    if (!actions || !store) {
      this.warn("Modul pengaturan mic tidak ditemukan. Matikan echo cancellation dan noise suppression manual di Voice & Video.");
      return;
    }

    if (!this.savedProcessing) {
      const read = (name) => {
        try {
          return typeof store[name] === "function" ? store[name]() : undefined;
        } catch (e) {
          return undefined;
        }
      };
      this.savedProcessing = {
        echo: read("getEchoCancellation"),
        noise: read("getNoiseSuppression"),
        agc: read("getAutomaticGainControl"),
      };
      this.debug("Pengaturan mic asli disimpan:", this.savedProcessing);
    }

    this.setProcessing(actions, { echo: false, noise: false, agc: false });
  }

  setProcessing(actions, v) {
    const call = (fn, value) => {
      if (value === undefined || typeof actions[fn] !== "function") return;
      try {
        actions[fn](value);
      } catch (e) {
        this.warn(`${fn} gagal:`, e);
      }
    };
    call("setEchoCancellation", v.echo);
    call("setNoiseSuppression", v.noise);
    call("setAutomaticGainControl", v.agc);
  }

  restoreProcessing() {
    if (!this.savedProcessing) return;
    const actions = this.getProcessingActions();
    if (actions) this.setProcessing(actions, this.savedProcessing);
    this.savedProcessing = null;
  }

  /* ---------- lifecycle ---------- */

  start() {
    if (this.settings.disableProcessing) this.applyProcessing();
    this.detect();
    this.timer = setInterval(() => this.detect(), 2000);
    this.toast("StereoVoice aktif. Keluar lalu masuk lagi ke voice channel.", "success");
  }

  stop() {
    if (this.timer) clearInterval(this.timer);
    this.timer = null;
    try {
      BdApi.Patcher.unpatchAll(this.id);
    } catch (e) {
      this.warn("unpatchAll gagal:", e);
    }
    this.patchedTargets = new WeakSet();
    this.hooks = { connectionsAdd: false, wrapperPrototype: false };
    if (this.settings.restoreProcessing) this.restoreProcessing();
    this.toast("StereoVoice dimatikan. Keluar lalu masuk lagi ke voice channel.", "info");
  }

  describe(obj) {
    if (!obj || typeof obj !== "object") return typeof obj;
    const proto = Object.getPrototypeOf(obj);
    return {
      ctor: proto && proto.constructor ? proto.constructor.name : null,
      ownKeys: Object.keys(obj).slice(0, 25),
      protoKeys: proto && proto !== Object.prototype ? Object.getOwnPropertyNames(proto).slice(0, 40) : [],
    };
  }

  diagnose() {
    const store = this.getStore();
    const engine = this.getEngine();
    const conns = this.getConnections();
    const raw = engine && engine.connections;
    const info = {
      storeFound: !!store,
      engineFound: !!engine,
      engineKeys: engine ? this.describe(engine) : null,
      connectionsType: raw ? (raw.constructor && raw.constructor.name) || typeof raw : String(raw),
      connectionCount: conns.length,
      connectionsWithSetTransportOptions: conns.filter((c) => this.resolveConnection(c)).length,
      firstConnection: conns[0] ? this.describe(conns[0]) : null,
      firstConnectionInner: conns[0] && conns[0].conn ? this.describe(conns[0].conn) : null,
      hooks: { ...this.hooks },
      wrapperPrototypeFound: !!this.getWrapperPrototype(),
      processingActionsFound: !!this.getProcessingActions(),
      lastSetTransportOptions: this.lastSeen,
      settings: { ...this.settings },
    };
    this.log("Diagnosa:", info);
    return info;
  }

  getSettingsPanel() {
    return BdApi.UI.buildSettingsPanel({
      settings: [
        {
          type: "switch",
          id: "stereo",
          name: "Stereo (2 kanal)",
          note: "Hanya berguna jika input device memang stereo (mis. Stereo Mix, mic binaural, virtual cable).",
          value: this.settings.stereo,
        },
        {
          type: "slider",
          id: "bitrate",
          name: "Bitrate",
          note: "Makin tinggi makin bagus, tapi server voice bisa membatasi. 128 sampai 256 kbps cukup untuk stereo.",
          value: this.settings.bitrate,
          min: 32,
          max: 510,
          step: 8,
          units: "kbps",
          markers: [32, 64, 96, 128, 192, 256, 384, 510],
          stickToMarkers: false,
        },
        {
          type: "switch",
          id: "disableProcessing",
          name: "Matikan echo cancellation, noise suppression, dan AGC",
          note: "Proses ini merusak stereo dan kualitas musik. Pakai headphone supaya tidak ada gema.",
          value: this.settings.disableProcessing,
        },
        {
          type: "switch",
          id: "restoreProcessing",
          name: "Kembalikan pengaturan mic saat plugin dimatikan",
          value: this.settings.restoreProcessing,
        },
        {
          type: "switch",
          id: "debug",
          name: "Debug log",
          note: "Catat panggilan setTransportOptions di console (Ctrl+Shift+I).",
          value: this.settings.debug,
        },
      ],
      onChange: (category, id, value) => {
        this.settings[id] = id === "bitrate" ? this.clampBitrate(value) : value;
        this.saveSettings();
        if (id === "disableProcessing") {
          if (value) this.applyProcessing();
          else if (this.settings.restoreProcessing) this.restoreProcessing();
        }
        if (id === "stereo" || id === "bitrate") this.reapply();
      },
    });
  }
};
