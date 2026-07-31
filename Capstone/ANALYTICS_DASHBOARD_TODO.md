# Analytics Dashboard — Sisa Pekerjaan

## Sudah selesai
- Migrasi SQLite → PostgreSQL (schema `app` + `analytics`), migrator script idempoten, sudah dijalankan di lokal dan di EC2 (data production ter-migrasi, app tetap jalan di SQLite — belum cutover).
- Backend analytics: klasifikasi topik rule-based, tabel `canonical_interactions` + `daily_topic_aggregates`, endpoint `summary`, `topics`, `trend`, `active-users`, `logs-by-topic`.
- Dashboard React (Vite + Tailwind + Recharts) di-build jadi bundle statis, ditanam ke dalam `frontend/web/index.html` (nav "Analytics"), gaya visual disamakan dengan tema utama (ink/paper/red, JetBrains Mono/Instrument Sans).
- Metrik direvisi jadi HR-relevant: Total Questions, Active Users, Most Discussed Topic, Negative Feedback (KPI error/fallback dihapus).
- Klik topik/user di dashboard sudah dikabelkan untuk lompat ke halaman Logs dengan filter (lewat `window.navigateToLogsWithFilter`).
- Keamanan: port Postgres di EC2 sudah ditutup lagi ke `127.0.0.1` (tidak exposed ke internet), rencana Data Studio dibatalkan.

## Belum selesai / perlu verifikasi
1. **Verifikasi visual & fungsional end-to-end** — belum ada konfirmasi bahwa build terbaru (setelah restyle + fitur klik-filter) benar-benar tampil bagus dan berfungsi di browser. Sesi terakhir kepotong sebelum restart server + testing selesai.
2. **Testing tombol klik topik → Logs** dan **klik user → Logs** — kode sudah ditulis tapi belum dicoba klik langsung di browser.
3. **Cek ulang endpoint `logs-by-topic`** dengan data nyata (baru dibuat, belum pernah dipanggil).
4. **Bersihkan file dev/testing sementara** (`_dev_inject_session.html`, log uvicorn/vite, dll) sebelum commit.
5. **Commit + push** — belum dilakukan sama sekali untuk perubahan dashboard (menunggu approval visual dari user sesuai kesepakatan awal).
6. **Deploy ke EC2** — ditahan total, termasuk build dashboard React di server produksi (belum ada Dockerfile/CI step untuk build Vite di sana).
7. **Keputusan cutover SQLite → Postgres di production** — belum diambil, masih murni data mirror untuk analytics.
8. Opsional/belum dibahas lagi: apakah "Active Users" perlu tampilkan nama asli atau tetap pseudonymous di level UI (sudah pakai email asli sesuai keputusan terakhir, tapi belum direview user).
