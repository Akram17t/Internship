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
| State/cache | `backend/cache_db.py`, `backend/semantic_cache.py` | Conversation store, semantic cache, dan metadata state |

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

### `backend/cache_db.py`

State SQLite lokal:
- schema `conversation_messages`
- schema `semantic_cache_entries`
- migrasi legacy `conversations.json` sekali jalan jika file lama masih ada
- cleanup conversation berdasarkan TTL dan batas jumlah pesan
- helper insert/lookup semantic cache exact

### `backend/semantic_cache.py`

Semantic answer cache:
- `lookup_semantic_cache()` mencoba exact lookup lalu vector similarity lookup
- `store_semantic_cache()` menyimpan payload ke SQLite dan embedding key ke Chroma
- `reset_semantic_cache()` menghapus metadata SQLite dan collection Chroma semantic cache setelah reindex
- guard cache memakai `active_index`, `MODEL`, `EMBED_MODEL`, citation, fallback answer, dan threshold

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

Logic auto-fill PDF form:
- `_segment_label()`
- `_scan_form_fields()`
- `_unique_form_fields()`
- `_fill_form_placeholders()`
- `_load_form_schema_payloads()`
- `get_form_schema()`
- `fill_schema_form()`
- `_resolve_form_path()`

### `backend/api/routes_public.py`

Endpoint publik:
- `GET /health`
- `POST /query`
- `GET /api/faq`
- `GET /api/flowcharts/{flowchart_id}`
- `GET /api/documents/{path}`
- `GET /api/forms/schema`
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
3. Kumpulkan semua form PDF yang tersedia
4. Kirim question + context + katalog form ke run_knowledge_crew()
5. `run_knowledge_crew()` rewrite follow-up jika perlu
6. Cek semantic cache memakai standalone question
7. Jika cache miss, retrieval Chroma + rerank lalu generate jawaban
8. Simpan semantic cache jika jawaban punya citation dan bukan fallback
9. Simpan turn baru ke SQLite `app_state.db`
10. Bentuk CitationResponse, form_downloads, dan flowcharts untuk frontend
11. Return answer + citations + form_downloads + flowcharts + conversation_id
```

Modul yang terlibat:
- `backend/api/routes_public.py`
- `backend/api/cache_store.py`
- `backend/api/storage.py`
- `backend/api/flowchart_service.py`
- `backend/researcher_crew/main.py`
- `backend/researcher_crew/tools/custom_tool.py`
- `backend/semantic_cache.py`
- `backend/preprocessing/vectorstore.py`

---

## 4. Semantic Cache Flow

Semantic cache berjalan di dalam `run_knowledge_crew()` setelah pertanyaan final
ditentukan oleh context switching.

```text
1. Normalisasi standalone question
2. Exact lookup ke SQLite `semantic_cache_entries`
3. Jika exact miss, similarity lookup ke `backend/cache/semantic_chroma`
4. Validasi metadata: active_index, MODEL, EMBED_MODEL
5. Validasi payload: answer tidak fallback dan citation tidak kosong
6. Jika hit, return cached answer tanpa retrieval/generation
7. Jika miss, lanjut RAG normal lalu store cache jika valid
```

Storage semantic cache:
- SQLite `backend/cache/app_state.db` menyimpan payload jawaban dan metadata.
- Chroma `backend/cache/semantic_chroma` menyimpan embedding normalized question.

Reset semantic cache:
- insert/update/delete dokumen hanya menandai `requires_reindex=True`.
- cache lama dihapus saat admin menjalankan `POST /api/admin/reindex`.
- `backend/preprocessing/ingest.py` memanggil `reset_semantic_cache()` setelah `rebuild_vectorstore()`.

---

## 5. FAQ Flow

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

## 6. Dokumen dan Reindex

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
- rebuild vectorstore dari dokumen terbaru
- hapus semantic cache lama lewat `reset_semantic_cache()`

---

## 7. Auto-Fill Form PDF

Flow form fill:

```text
1. User klik "Isi & download"
2. Frontend coba GET /api/forms/schema
3. Jika schema ada, browser render preview PDF + field panel schema
4. Jika schema tidak ada, frontend fallback ke GET /api/forms/fields
5. forms_service.py scan placeholder PDF untuk mode legacy
6. User isi nilai / upload signature
7. Frontend panggil POST /api/forms/fill
8. Jika schema form, forms_service.py render PDF schema-driven di memory
9. Jika legacy form, forms_service.py isi placeholder PDF di memory
10. Backend kirim file PDF hasil ke browser
```

Helper penting:
- `_scan_form_fields()` mendeteksi placeholder bracket dari blok awal PDF
- `_unique_form_fields()` menghapus duplikasi label
- `_fill_form_placeholders()` mengisi semua placeholder dengan label yang cocok
- `get_form_schema()` membaca schema template dari `backend/form_schemas/*.json`
- `fill_schema_form()` menulis `text`, `textarea`, `date`, `checkbox`, dan `signature_image` ke PDF

---

## 8. RAG Layer

### `backend/researcher_crew/main.py`

Fungsi penting:
- `_rewrite_query()` untuk context switching
- `lookup_semantic_cache()` dipanggil sebelum retrieval
- `store_semantic_cache()` dipanggil setelah jawaban final valid
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

## 9. Ingestion Layer

### `backend/preprocessing/loader.py`
- load PDF, DOCX, TXT
- normalisasi metadata dokumen
- skip file form dari embedding
- untuk PDF, panggil `extract_flowchart_documents()`

### `backend/preprocessing/chunker.py`
- bersihkan noise SOP
- deteksi heading
- pecah dokumen per section
- merge section lanjutan
- simpan konteks tabel
- pecah lagi jadi chunk final
- masukkan flowchart chunk yang confidence-nya layak

### `backend/preprocessing/flowchart_extractor.py`
- deteksi kandidat halaman flowchart dari heading `ALUR PROSES`
- ambil image terbesar pada halaman kandidat
- panggil Ollama vision untuk ekstrak node/edge flowchart
- validasi graph dan coba repair edge yang hilang
- cache payload JSON ke `backend/cache/flowcharts`

### `backend/preprocessing/embedding.py`
- buat `OllamaEmbeddings`

### `backend/preprocessing/vectorstore.py`
- buka Chroma aktif
- rebuild index baru
- rerank hasil retrieval
- filter hasil dengan `RETRIEVAL_MIN_SCORE`

### `backend/preprocessing/ingest.py`
- load dokumen
- ekstrak flowchart ketika enabled
- chunk dokumen
- rebuild vectorstore
- tulis marker citation schema
- reset semantic cache lama

---

## 10. Penyimpanan

| Lokasi | Isi |
|---|---|
| `backend/data/` | Dokumen sumber dan template form |
| `backend/chroma_db/` | ChromaDB + marker active index |
| `backend/cache/app_state.db` | Riwayat percakapan + semantic cache |
| `backend/cache/semantic_chroma` | Vector store untuk pertanyaan semantic cache |
| `backend/cache/flowcharts` | Cache JSON hasil ekstraksi flowchart |
| `backend/cache/faqs.json` | FAQ tersimpan |
| `backend/cache/admin.json` | Config admin lokal |

---

## 11. Catatan Penting

- Banyak docs lama menyebut `backend/api/main.py` sebagai file besar tunggal. Itu sudah tidak berlaku.
- Untuk baca flow API sekarang, mulai dari `routes_public.py` atau `routes_admin.py`.
- Untuk cari helper, lanjut ke `storage.py`, `cache_store.py`, `auth.py`, `faq_service.py`, atau `forms_service.py`.
- Untuk cache jawaban, mulai dari `backend/semantic_cache.py` dan `backend/cache_db.py`.
- Untuk ingestion yang memengaruhi cache, mulai dari `backend/preprocessing/ingest.py`.
