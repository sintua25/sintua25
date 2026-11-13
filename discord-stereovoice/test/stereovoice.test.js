// Tes sederhana dengan BdApi dan MediaEngineStore palsu. Jalankan: node --test discord-stereovoice/test
const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");

const PLUGIN = path.join(__dirname, "..", "StereoVoice.plugin.js");

/* ---------- Discord palsu ---------- */

function makeFakePatcher() {
  const undo = [];
  const wrap = (obj, name, kind, cb) => {
    const original = obj[name];
    const hadOwn = Object.prototype.hasOwnProperty.call(obj, name);
    obj[name] = function (...args) {
      if (kind === "before") cb(this, args);
      const ret = original.apply(this, args);
      if (kind === "after") cb(this, args, ret);
      return ret;
    };
    undo.push(() => {
      if (hadOwn) obj[name] = original;
      else delete obj[name];
    });
  };
  return {
    before: (_id, obj, name, cb) => wrap(obj, name, "before", cb),
    after: (_id, obj, name, cb) => wrap(obj, name, "after", cb),
    unpatchAll: () => undo.splice(0).reverse().forEach((f) => f()),
  };
}

// Koneksi "native": setTransportOptions milik instance (bukan prototype).
function makeNativeConn() {
  const conn = { received: [] };
  conn.setTransportOptions = function (opts) {
    this.received.push(opts);
  };
  return conn;
}

// Wrapper seperti di Discord: punya .conn dan updateVideoQuality di prototype.
class FakeWrapper {
  constructor() {
    this.conn = makeNativeConn();
  }
  updateVideoQuality() {}
  setCodecs() {
    this.conn.setTransportOptions({
      audioEncoder: { type: 120, name: "opus", freq: 48000, pacsize: 960, channels: 1, rate: 64000, params: {} },
      encodingVoiceBitRate: 64000,
    });
  }
  setVoiceBitRate(bps) {
    this.conn.setTransportOptions({ encodingVoiceBitRate: bps });
  }
}

function setup({ mangledActions = false, savedSettings = {} } = {}) {
  const engine = { connections: new Set() };
  const store = {
    getMediaEngine: () => engine,
    getEchoCancellation: () => true,
    getNoiseSuppression: () => true,
    getAutomaticGainControl: () => false,
  };
  const calls = [];
  const plainActions = {
    setEchoCancellation: (v) => calls.push(["echo", v]),
    setNoiseSuppression: (v) => calls.push(["noise", v]),
    setAutomaticGainControl: (v) => calls.push(["agc", v]),
  };
  const data = { settings: savedSettings };

  global.BdApi = {
    Logger: { info: () => {}, warn: () => {} },
    Data: { load: (_id, k) => data[k], save: (_id, k, v) => (data[k] = v) },
    UI: { showToast: () => {}, buildSettingsPanel: (o) => o },
    Patcher: makeFakePatcher(),
    Webpack: {
      Filters: {
        byPrototypeKeys: (k) => (m) => m && m.prototype && typeof m.prototype[k] === "function",
        byStrings: (s) => (f) => typeof f === "function" && String(f).includes(s),
      },
      getStore: (name) => (name === "MediaEngineStore" ? store : null),
      getModule: (filter) => {
        const mods = [FakeWrapper];
        if (!mangledActions) mods.push(plainActions);
        return mods.find((m) => filter(m)) || null;
      },
      getMangled: (_filter, mappers) => {
        if (!mangledActions) return null;
        // simulasi modul minified: fungsi dikenali dari nama action dispatch
        const fns = [
          (v) => calls.push(["echo", v, "AUDIO_SET_ECHO_CANCELLATION"]),
          (v) => calls.push(["noise", v, "AUDIO_SET_NOISE_SUPPRESSION"]),
          (v) => calls.push(["agc", v, "AUDIO_SET_AUTOMATIC_GAIN_CONTROL"]),
        ];
        const out = {};
        for (const [k, f] of Object.entries(mappers)) out[k] = fns.find(f);
        return out;
      },
    },
  };

  delete require.cache[require.resolve(PLUGIN)];
  const Plugin = require(PLUGIN);
  const plugin = new Plugin({ name: "StereoVoice" });
  return { plugin, engine, store, calls, data };
}

const fullOpts = () => ({
  audioEncoder: { type: 120, name: "opus", freq: 48000, pacsize: 960, channels: 1, rate: 64000, params: {} },
  encodingVoiceBitRate: 64000,
  fec: true,
});

/* ---------- tes ---------- */

test("transform: ubah ke stereo + bitrate, objek asli tidak diubah", () => {
  const { plugin } = setup();
  const before = fullOpts();
  const after = plugin.transform(before);
  assert.equal(after.audioEncoder.channels, 2);
  assert.equal(after.audioEncoder.params.stereo, "1");
  assert.equal(after.audioEncoder.rate, 256000);
  assert.equal(after.encodingVoiceBitRate, 256000);
  assert.equal(after.audioEncoder.freq, 48000);
  assert.equal(after.fec, true);
  assert.equal(before.audioEncoder.channels, 1, "objek asli tetap");
});

test("transform: update parsial tanpa audioEncoder tidak disentuh", () => {
  const { plugin } = setup();
  const partial = { selfMute: true };
  assert.equal(plugin.transform(partial), partial);
  assert.equal(plugin.transform(undefined), undefined);
});

test("transform: update bitrate saja diganti nilainya, bentuk tetap", () => {
  const { plugin } = setup();
  assert.deepEqual(plugin.transform({ encodingVoiceBitRate: 64000 }), { encodingVoiceBitRate: 256000 });
});

test("alur nyata: setCodecs lalu setVoiceBitRate tetap stereo 256 kbps", () => {
  const { plugin, engine } = setup();
  engine.connections = { add: undefined }; // hanya hook prototype wrapper
  plugin.start();
  const w = new FakeWrapper();
  w.setCodecs();
  w.setVoiceBitRate(64000);
  assert.equal(w.conn.received[0].audioEncoder.channels, 2);
  assert.deepEqual(w.conn.received[1], { encodingVoiceBitRate: 256000 });
  plugin.stop();
});

test("detect: koneksi yang sudah ada dipatch (instance native di dalam wrapper)", () => {
  const { plugin, engine } = setup();
  const w = new FakeWrapper();
  engine.connections.add(w);
  plugin.start();
  w.conn.setTransportOptions(fullOpts());
  assert.equal(w.conn.received[0].audioEncoder.channels, 2);
  plugin.stop();
});

test("koneksi baru dipatch SEBELUM panggilan pertama (hook connections.add)", () => {
  const { plugin, engine } = setup();
  plugin.start();
  const w = new FakeWrapper();
  engine.connections.add(w); // Discord menambah koneksi...
  w.conn.setTransportOptions(fullOpts()); // ...lalu langsung kirim opsi pertama
  assert.equal(w.conn.received[0].audioEncoder.channels, 2);
  assert.equal(plugin.hooks.connectionsAdd, true);
  plugin.stop();
});

test("koneksi baru dipatch lewat hook updateVideoQuality juga", () => {
  const { plugin, engine } = setup();
  engine.connections = { add: undefined }; // anggap hook A tidak tersedia
  plugin.start();
  const w = new FakeWrapper();
  w.updateVideoQuality();
  w.conn.setTransportOptions(fullOpts());
  assert.equal(w.conn.received[0].audioEncoder.channels, 2);
  assert.equal(plugin.hooks.wrapperPrototype, true);
  plugin.stop();
});

test("reapply: mematikan stereo benar-benar kembali ke 1 kanal", () => {
  const { plugin, engine } = setup();
  const w = new FakeWrapper();
  engine.connections.add(w);
  plugin.start();
  w.conn.setTransportOptions(fullOpts());
  w.conn.setTransportOptions({ selfMute: true }); // parsial tidak menimpa opsi tersimpan

  const panel = plugin.getSettingsPanel();
  panel.onChange(null, "stereo", false);
  const last = w.conn.received.at(-1);
  assert.equal(last.audioEncoder.channels, 1);
  assert.equal(last.audioEncoder.rate, 256000);

  panel.onChange(null, "bitrate", 128);
  assert.equal(w.conn.received.at(-1).encodingVoiceBitRate, 128000);
  plugin.stop();
});

test("stop: patch dilepas, opsi tidak diubah lagi", () => {
  const { plugin, engine } = setup();
  const w = new FakeWrapper();
  engine.connections.add(w);
  plugin.start();
  plugin.stop();
  w.conn.setTransportOptions(fullOpts());
  assert.equal(w.conn.received[0].audioEncoder.channels, 1);
  assert.equal(Object.prototype.hasOwnProperty.call(engine.connections, "add"), false);
});

test("pemrosesan mic: dimatikan saat start, dikembalikan saat stop", () => {
  const { plugin, calls } = setup();
  plugin.start();
  assert.deepEqual(calls.splice(0), [["echo", false], ["noise", false], ["agc", false]]);
  plugin.stop();
  assert.deepEqual(calls, [["echo", true], ["noise", true], ["agc", false]]);
});

test("pemrosesan mic: modul minified ditemukan lewat nama action", () => {
  const { plugin, calls } = setup({ mangledActions: true });
  plugin.start();
  assert.deepEqual(calls.map((c) => c.slice(0, 2)), [["echo", false], ["noise", false], ["agc", false]]);
  plugin.stop();
});

test("bitrate tersimpan di luar batas dijepit ke 8..510", () => {
  assert.equal(setup({ savedSettings: { bitrate: 9999 } }).plugin.settings.bitrate, 510);
  assert.equal(setup({ savedSettings: { bitrate: "abc" } }).plugin.settings.bitrate, 256);
});

test("diagnose: melaporkan store, engine, koneksi, hook", () => {
  const { plugin, engine } = setup();
  engine.connections.add(new FakeWrapper());
  plugin.start();
  const info = plugin.diagnose();
  assert.equal(info.storeFound, true);
  assert.equal(info.engineFound, true);
  assert.equal(info.connectionsType, "Set");
  assert.equal(info.connectionCount, 1);
  assert.equal(info.connectionsWithSetTransportOptions, 1);
  assert.equal(info.hooks.connectionsAdd, true);
  assert.equal(info.processingActionsFound, true);
  plugin.stop();
});
