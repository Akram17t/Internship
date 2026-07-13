# Backend Reference - ICS SOP & Knowledge Assistant

Dokumentasi backend ini sudah disesuaikan dengan struktur kode terbaru. Fokusnya
adalah menjelaskan file penting, responsibility tiap modul, dan alur runtime utama.
Frontend tidak dibahas detail di sini.

---

## 1. Gambaran Umum

Backend terdiri dari 4 area besar:

| Area | Folder/File | Peran |
|---|---|---|
| Config | `backend/settings.py` | Loader `.env` dan helper env |
| API layer | `backend/api/` | FastAPI app, route publik/admin, helper service |
| RAG layer | `backend/researcher_crew/` | Rewrite query, retrieval, generation chat dan FAQ |
| Preprocessing | `backend/preprocessing/` | Ingestion dokumen ke ChromaDB |

`backend/api/main.py` sekarang bukan lagi file besar berisi semua logic. File itu
hanya entrypoint tipis untuk mengekspor `app` dan memuat modul route.

---

## 2. Struktur API Layer

### `backend/api/core.py`

Modul dasar API:
- buat `app = FastAPI(...)`
- simpan konstanta bersama seperti `FRONTEND_DIR`, `ASSETS_DIR`,
  `EMBEDDABLE_EXTENSIONS`, `LIBRARY_EXTENSIONS`
- simpan lock bersama seperti `FAQ_LOCK`, `REINDEX_LOCK`, `CONVERSATION_LOCK`
- mount `/assets` bila folder assets ada

### `backend/api/models.py`

Semua schema request/response Pydantic:
- `QueryRequest`, `QueryResponse`
- `CitationResponse`, `FormDownloadResponse`
- `FAQItem`, `AdminFAQPayload`, `AdminFAQResponse`
- `AdminLoginPayload`, `AdminLoginResponse`
- `LibraryItem`, `AdminDocumentPayload`, `AdminDocumentResponse`
- `AdminReindexResponse`, `FormFillPayload`

### `backend/api/storage.py`

Helper untuk file dan library:
- `_get_data_dir()`
- `_document_kind_for_path()`
- `_is_embeddable_path()`
- `_to_library_item()`, `_iter_library_items()`
- `_format_form_display_name()`
- `_iter_form_downloads()`, `_iter_form_paths()`
- `_available_form_catalog()`
- `_selected_form_downloads()`
- `_resolve_document_path()`
- `_decode_document()`

### `backend/api/cache_store.py`

Helper cache lokal:
- `admin.json`: `_load_admin_config()`, `_save_admin_config()`
- context percakapan: `_get_conversation_context()`,
  `_append_conversation_turn()` via `backend/cache_db.py`
- `faqs.json`: `_load_faqs()`, `_save_faqs()`, `_find_faq_index()`
- helper normalisasi citation dan FAQ

### `backend/api/auth.py`

Helper autentikasi admin:
- `_create_admin_token()`
- `_verify_admin_token()`
- `_require_admin()`
- helper email/nama/password/session secret admin

### `backend/api/faq_service.py`

Logic FAQ yang bukan route:
- `_build_faq_item()` untuk generate FAQ dari RAG
- `_is_unusable_faq_answer()` untuk menolak FAQ tanpa evidence
- `_pinned_faq_items()` untuk organogram
- helper gambar pinned FAQ

### `backend/api/forms_service.py`

Logic auto-fill Excel:
- `_field_label()`
- `_scan_form_fields()`
- `_unique_form_fields()`
- `_fill_form_placeholders()`
- `_resolve_form_path()`

### `backend/api/routes_public.py`

Endpoint publik:
- `GET /health`
- `POST /query`
- `GET /api/faq`
- `GET /api/documents/{path}`
- `GET /api/forms/fields`
- `POST /api/forms/fill`
- `GET /`

### `backend/api/routes_admin.py`

Endpoint admin:
- `POST /api/admin/login`
- `POST /api/admin/faq-image`
- `POST /api/admin/faq`
- `PUT /api/admin/faq/{id}`
- `DELETE /api/admin/faq/{id}`
- `GET /api/library`
- `POST /api/admin/documents`
- `DELETE /api/admin/documents/{path}`
- `POST /api/admin/reindex`

### `backend/api/main.py`

Entry point tipis:
- import `app` dari `core.py`
- import `routes_public` dan `routes_admin` agar endpoint terdaftar

---

## 3. Chat Flow

Endpoint chat ada di `backend/api/routes_public.py` lewat `query_knowledge_base()`.

Alurnya:

```text
1. Bersihkan / buat conversation_id
2. Ambil context percakapan dari SQLite `app_state.db`
3. Kumpulkan semua form xlsx yang tersedia
4. Kirim question + context + katalog form ke run_knowledge_crew()
5. Simpan turn baru ke SQLite `app_state.db`
6. Bentuk CitationResponse untuk frontend
7. Jika jawaban supported, map selected_forms dari AI ke form_downloads
8. Return answer + citations + form_downloads + conversation_id
```

Modul yang terlibat:
- `backend/api/routes_public.py`
- `backend/api/cache_store.py`
- `backend/api/storage.py`
- `backend/researcher_crew/main.py`
- `backend/researcher_crew/tools/custom_tool.py`
- `backend/preprocessing/vectorstore.py`

---

## 4. FAQ Flow

FAQ publik dibaca dari:
- pinned FAQ di `backend/api/faq_service.py`
- FAQ tersimpan di `backend/cache/faqs.json`

FAQ admin dibuat lewat `backend/api/routes_admin.py`:

```text
1. Admin kirim pertanyaan FAQ
2. routes_admin.py panggil _build_faq_item()
3. faq_service.py panggil run_faq_crew()
4. researcher_crew/main.py ambil evidence via retrieve_knowledge()
5. Jika tidak ada citation relevan, FAQ ditolak
6. Jika ada, Ollama buat jawaban FAQ singkat
7. FAQ disimpan ke faqs.json
```

---

## 5. Dokumen dan Reindex

### Upload / Replace

`POST /api/admin/documents`:
- validasi token admin
- validasi extension
- decode base64
- insert file baru atau replace file lama
- jika file embeddable (`pdf/docx/txt`), set `requires_reindex=True`

### Delete

`DELETE /api/admin/documents/{path}`:
- validasi token admin
- validasi path aman
- hapus file
- tandai apakah butuh reindex

### Reindex

`POST /api/admin/reindex`:
- validasi token admin
- pakai `REINDEX_LOCK`
- panggil `backend.preprocessing.ingest.main()`

---

## 6. Auto-Fill Form Excel

Flow form fill:

```text
1. User klik "Isi & download"
2. Frontend panggil GET /api/forms/fields
3. forms_service.py scan placeholder xlsx
4. Frontend render field hasil scan
5. User isi nilai
6. Frontend panggil POST /api/forms/fill
7. forms_service.py isi workbook di memory
8. Backend kirim file xlsx hasil ke browser
```

Helper penting:
- `_scan_form_fields()` mendeteksi field dari blok awal sheet
- `_unique_form_fields()` menghapus duplikasi label
- `_fill_form_placeholders()` mengisi semua placeholder dengan label yang cocok

---

## 7. RAG Layer

### `backend/researcher_crew/main.py`

Fungsi penting:
- `_rewrite_query()` untuk context switching
- `run_knowledge_crew()` untuk chat
- `run_faq_crew()` untuk FAQ
- `_generate_answer()` lewat CrewAI
- `_generate_faq_answer()` lewat Ollama langsung
- `_split_form_selection()` untuk ambil `FORM_SELECTION`

### `backend/researcher_crew/crew.py`

Definisi CrewAI:
- `_llm()`
- `answer_writer()`
- `chat_answer_task()`
- `crew()`

### `backend/researcher_crew/tools/custom_tool.py`

Retrieval evidence:
- `retrieve_knowledge()`
- `_citation_from_document()`

---

## 8. Ingestion Layer

### `backend/preprocessing/loader.py`
- load PDF, DOCX, TXT
- normalisasi metadata dokumen

### `backend/preprocessing/chunker.py`
- bersihkan noise SOP
- deteksi heading
- pecah dokumen per section
- pecah lagi jadi chunk final

### `backend/preprocessing/embedding.py`
- buat `OllamaEmbeddings`

### `backend/preprocessing/vectorstore.py`
- buka Chroma aktif
- rebuild index baru
- rerank hasil retrieval
- filter hasil dengan `RETRIEVAL_MIN_SCORE`

### `backend/preprocessing/ingest.py`
- load dokumen
- chunk dokumen
- rebuild vectorstore
- tulis marker citation schema

---

## 9. Penyimpanan

| Lokasi | Isi |
|---|---|
| `backend/data/` | Dokumen sumber dan template form |
| `backend/chroma_db/` | ChromaDB + marker active index |
| `backend/cache/app_state.db` | Riwayat percakapan + semantic cache |
| `backend/cache/faqs.json` | FAQ tersimpan |
| `backend/cache/admin.json` | Config admin lokal |

---

## 10. Catatan Penting

- Banyak docs lama menyebut `backend/api/main.py` sebagai file besar tunggal. Itu sudah tidak berlaku.
- Untuk baca flow API sekarang, mulai dari `routes_public.py` atau `routes_admin.py`.
- Untuk cari helper, lanjut ke `storage.py`, `cache_store.py`, `auth.py`, `faq_service.py`, atau `forms_service.py`.
