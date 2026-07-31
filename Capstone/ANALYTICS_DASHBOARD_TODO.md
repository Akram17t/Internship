# Analytics Dashboard — Sisa Pekerjaan

Status terakhir: server dari `run.bat` hidup dan `/health` mengembalikan HTTP 200. Dua defect runtime sudah diperbaiki di working tree, tetapi validasi final setelah defect kedua belum selesai karena sesi testing terpotong.

## P0 — wajib sebelum dianggap selesai

- [ ] **Ulangi end-to-end dari `run.bat` setelah patch timestamp.** Jalankan aplikasi melalui `run.bat`, bukan Python global atau TestClient.
- [ ] **Uji seluruh halaman Logs dengan date range melalui HTTP nyata.** Endpoint yang wajib 200: `/api/admin/logs`, `/api/admin/logs/summary`, dan `/api/admin/logs/sessions`. Pastikan tidak muncul lagi error `TIMESTAMPTZ >= VARCHAR`.
- [ ] **Uji Analytics → Logs di Chrome terhadap server/API nyata.** Klik active user, topic row, bar chart, dan donut; pastikan filter Logs tampil dan data berhasil dimuat tanpa mock `fetch`.
- [ ] **Periksa log Uvicorn setelah semua klik.** Tidak boleh ada `Exception in ASGI application`, `ModuleNotFoundError`, atau SQLAlchemy/PostgreSQL error baru.
- [ ] **Jalankan full backend suite memakai interpreter yang sama dengan `run.bat`.** Command: `backend\researcher_crew\.venv\Scripts\python -m pytest backend\tests backend\researcher_crew\tests -q`.
- [ ] **Ulangi lint dan production build dashboard.** Jalankan `npm run lint` dan `npm run build` dari `frontend-dashboard`, lalu pastikan bundle embedded terbaru tetap dipakai aplikasi utama.
- [ ] **Bersihkan artefak E2E.** Hapus `.run-e2e.*`, harness/token sementara, dan file output template Vite yang tidak dipakai.

## Sudah diperbaiki, menunggu validasi final P0

- [x] `run.bat` sekarang mendeteksi dan memasang dependency PostgreSQL pinned ke `backend\researcher_crew\.venv` (`SQLAlchemy`, `psycopg`, `alembic`).
- [x] `run.bat` sekarang melakukan preflight koneksi dan schema PostgreSQL sebelum membuka FastAPI; database dev lokal dicoba dinyalakan melalui Docker Compose bila belum siap.
- [x] Missing `psycopg` sudah diperbaiki pada venv asli `run.bat`; startup terbaru menunjukkan PostgreSQL/schema ready dan Uvicorn running.
- [x] Filter tanggal repository PostgreSQL sudah mengubah ISO string menjadi `datetime` timezone-aware sebelum membandingkan kolom `TIMESTAMPTZ`.
- [x] Regression test timestamp ditambahkan; targeted suite pada venv `run.bat` lulus **9 passed**.
- [x] Endpoint analytics nyata sebelumnya lulus: refresh/summary/topics/trend/active-users/logs-by-topic HTTP 200, invalid topic HTTP 422.
- [x] Perhitungan distinct users, tipe `bucket_date`, validasi topik, SQL join drill-through, dan payload Recharts sudah diperbaiki.

## Keputusan user / production (bukan bagian validasi lokal)

- [ ] Review visual manusia terhadap tampilan akhir.
- [ ] Putuskan apakah Active Users tetap menampilkan email asli atau pseudonymous label.
- [ ] Commit dan push perubahan (belum dilakukan).
- [ ] Deploy ke EC2 (perlu persetujuan eksplisit karena mengubah production).
- [ ] Putuskan cutover production SQLite → PostgreSQL secara terpisah.
