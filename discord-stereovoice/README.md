# StereoVoice (plugin BetterDiscord)

Kirim suara mic stereo (Opus 2 kanal) dengan bitrate yang bisa diatur.

## Pasang
Salin `StereoVoice.plugin.js` ke folder plugin BetterDiscord, aktifkan, lalu keluar dan masuk lagi ke voice channel.

## Cek di Discord
1. Pengaturan plugin: nyalakan **Debug log**.
2. Buka console (Ctrl+Shift+I), masuk ke voice channel.
3. Jalankan: `BdApi.Plugins.get("StereoVoice").instance.diagnose()`

## Tes
`node --test discord-stereovoice/test/*.test.js` (Node 18+). Tes memakai BdApi dan MediaEngineStore palsu,
jadi hanya membuktikan logika plugin, bukan internal Discord yang sebenarnya.
