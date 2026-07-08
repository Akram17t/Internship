# System Flows Capstone

Dokumen ini adalah peta cepat flow sistem yang sudah disesuaikan dengan struktur
backend terbaru. Referensi dibuat di level file/fungsi, bukan line number, supaya
tidak cepat basi saat ada refactor kecil.

## 1. Chat RAG dan Context Switching

### Diagram

```mermaid
flowchart TD
  A[User submit chat] --> B[frontend submitQuestion]
  B --> C[POST /query]
  C --> D[routes_public.query_knowledge_base]
  D --> E[cache_store ambil conversation context]
  E --> F[run_knowledge_crew]
  F --> G{Ada context?}
  G -->|Ya| H[Rewrite follow-up jadi standalone query]
  G -->|Tidak| I[Pakai pertanyaan asli]
  H --> J[Safety check rewrite]
  I --> K[retrieve_knowledge]
  J --> K
  K --> L[hybrid_search Chroma + rerank]
  L --> M{Citation ada?}
  M -->|Tidak| N[Jawab fallback tanpa sumber]
  M -->|Ya| O[Generate answer via CrewAI]
  O --> P[Rapikan citation marker dan form selection]
  P --> Q[Filter form_downloads jika jawaban supported]
  Q --> R[Simpan turn ke conversations.json]
  R --> S[Return answer + citations + forms]
```

### Fungsi dan lokasi

| Step | Fungsi | Lokasi |
|---|---|---|
| Submit chat dari frontend | `submitQuestion()` | `frontend/web/assets/app.js` |
| Endpoint chat | `query_knowledge_base()` | `backend/api/routes_public.py` |
| Ambil context | `_get_conversation_context()` | `backend/api/cache_store.py` |
| Simpan turn | `_append_conversation_turn()` | `backend/api/cache_store.py` |
| Rewrite follow-up | `_rewrite_query()` | `backend/researcher_crew/src/researcher_crew/main.py` |
| Safety rewrite | `_rewrite_is_safe()` | `backend/researcher_crew/src/researcher_crew/main.py` |
| Orkestrasi RAG chat | `run_knowledge_crew()` | `backend/researcher_crew/src/researcher_crew/main.py` |
| Retrieval evidence | `retrieve_knowledge()` | `backend/researcher_crew/src/researcher_crew/tools/custom_tool.py` |
| Vector search/rerank | `hybrid_search()` | `backend/preprocessing/vectorstore.py` |
| Generate jawaban | `_generate_answer()` | `backend/researcher_crew/src/researcher_crew/main.py` |
| CrewAI object | `ResearcherCrew.crew()` | `backend/researcher_crew/src/researcher_crew/crew.py` |
| Filter form untuk unsupported answer | `_answer_has_supported_form_context()` | `backend/api/storage.py` |
| Katalog form untuk AI | `_available_form_catalog()` | `backend/api/storage.py` |
| Map form pilihan AI | `_selected_form_downloads()` | `backend/api/storage.py` |

### Cara context switching bekerja

| Kondisi pertanyaan | Yang dilakukan sistem |
|---|---|
| Tidak ada context lama | Pertanyaan langsung dipakai untuk retrieval dan generation. |
| Ada context, tapi pertanyaan tidak merujuk ke sebelumnya | `_rewrite_query()` diarahkan untuk menyalin pertanyaan apa adanya. |
| Ada context dan pertanyaan merujuk ke sebelumnya | `_rewrite_query()` mengganti kata rujukan seperti `itu`, `tersebut`, `tadi`, `sebelumnya`, `barusan`, atau akhiran `-nya`. |
| Rewrite menambah angka/detail baru | `_rewrite_is_safe()` menolak rewrite dan balik ke pertanyaan asli. |

### Detail penting

| Item | Detail |
|---|---|
| File cache conversation | `backend/cache/conversations.json` |
| Batas context | Konstanta di `backend/api/core.py` |
| TTL conversation | `CONVERSATION_TTL` di `backend/api/core.py` |
| Model rewrite | Ollama direct lewat `_ollama_generate()` |
| Model answer | CrewAI single-agent `answer_writer` |
| Unsupported answer | Backend tidak menampilkan form download jika jawaban terdeteksi unsupported |

## 2. Admin Document dan Rebuild Embedding

### Diagram

```mermaid
flowchart TD
  A[Admin upload/update/delete file] --> B[Frontend document action]
  B --> C[POST/DELETE /api/admin/documents]
  C --> D[routes_admin validasi admin]
  D --> E[storage.py validasi path, extension, payload]
  E --> F[Tulis atau hapus file di DATA_DIR]
  F --> G{Embeddable? pdf/docx/txt}
  G -->|Tidak, xlsx form| H[Tidak perlu rebuild]
  G -->|Ya| I[Tandai perlu rebuild]
  I --> J[Admin klik Rebuild embeddings]
  J --> K[POST /api/admin/reindex]
  K --> L[preprocessing.ingest.main]
  L --> M[load_documents]
  M --> N[chunk_documents]
  N --> O[rebuild_vectorstore]
```

### Fungsi dan lokasi

| Step | Fungsi | Lokasi |
|---|---|---|
| Upload banyak file | `saveDocuments()` | `frontend/web/assets/app.js` |
| Upload/update satu file | `saveDocument()` | `frontend/web/assets/app.js` |
| Delete dokumen UI | `deleteDocument()` | `frontend/web/assets/app.js` |
| Rebuild embeddings UI | `rebuildEmbeddings()` | `frontend/web/assets/app.js` |
| Insert/update backend | `save_document()` | `backend/api/routes_admin.py` |
| Delete backend | `delete_document()` | `backend/api/routes_admin.py` |
| Rebuild backend | `reindex_documents()` | `backend/api/routes_admin.py` |
| Load source docs | `load_documents()` | `backend/preprocessing/loader.py` |
| Chunk docs | `chunk_documents()` | `backend/preprocessing/chunker.py` |
| Build Chroma index | `rebuild_vectorstore()` | `backend/preprocessing/vectorstore.py` |
| Orkestrasi ingest | `main()` | `backend/preprocessing/ingest.py` |

### Detail rebuild embedding

| Step | Detail |
|---|---|
| Lock | `REINDEX_LOCK` di `backend/api/core.py` |
| Dokumen yang masuk vector DB | `.pdf`, `.docx`, `.txt` |
| Dokumen yang tidak masuk vector DB | `.xlsx` form |
| Active index | `rebuild_vectorstore()` membuat folder `indexes/<uuid>` lalu menulis `.active-chroma-index` |
| Marker citation schema | `backend/preprocessing/ingest.py` menulis `.citation-metadata-v1` |

## 3. FAQ

### Diagram

```mermaid
flowchart TD
  A[Admin isi pertanyaan FAQ] --> B[saveFaq]
  B --> C[POST /api/admin/faq atau PUT /api/admin/faq/id]
  C --> D[routes_admin]
  D --> E[faq_service._build_faq_item]
  E --> F[run_faq_crew]
  F --> G[retrieve_knowledge]
  G --> H{Citation ada?}
  H -->|Tidak| I[422 no source]
  H -->|Ya| J[Generate FAQ via Ollama direct]
  J --> K[Validasi usable answer]
  K --> L[Simpan ke faqs.json]
  L --> M[Frontend loadFaqs + renderFaqs]
```

### Fungsi dan lokasi

| Step | Fungsi | Lokasi |
|---|---|---|
| Render FAQ list | `renderFaqs()` | `frontend/web/assets/app.js` |
| Load FAQ list | `loadFaqs()` | `frontend/web/assets/app.js` |
| Save FAQ frontend | `saveFaq()` | `frontend/web/assets/app.js` |
| GET FAQ | `get_faq()` | `backend/api/routes_public.py` |
| Build FAQ item | `_build_faq_item()` | `backend/api/faq_service.py` |
| Create FAQ | `create_faq()` | `backend/api/routes_admin.py` |
| Update FAQ | `update_faq()` | `backend/api/routes_admin.py` |
| Delete FAQ | `delete_faq()` | `backend/api/routes_admin.py` |
| Generate FAQ answer | `run_faq_crew()` | `backend/researcher_crew/src/researcher_crew/main.py` |
| FAQ prompt direct Ollama | `_generate_faq_answer()` | `backend/researcher_crew/src/researcher_crew/main.py` |

### Data FAQ

| Data | Lokasi |
|---|---|
| Stored FAQ | `backend/cache/faqs.json` |
| Pinned organogram FAQ | `_pinned_faq_items()` di `backend/api/faq_service.py` |
| Pinned image upload | `upload_pinned_faq_image()` di `backend/api/routes_admin.py` |

## 4. Auto-Fill Form Excel

### Diagram

```mermaid
flowchart TD
  A[Query masuk] --> B[_iter_form_downloads]
  B --> C[_available_form_catalog]
  C --> D[AI pilih form lewat FORM_SELECTION]
  D --> E[_selected_form_downloads]
  E --> F[Return form_downloads]
  F --> G[Frontend render Form yang bisa diunduh]
  G --> H{User pilih}
  H -->|Template| I[GET /api/documents/path]
  H -->|Isi & download| J[openFormFillModal]
  J --> K[GET /api/forms/fields]
  K --> L[Scan placeholder Excel]
  L --> M[Render input field]
  M --> N[User isi data]
  N --> O[POST /api/forms/fill]
  O --> P[Fill workbook in memory]
  P --> Q[Download xlsx terisi]
```

### Fungsi dan lokasi

| Step | Fungsi | Lokasi |
|---|---|---|
| Kumpulkan form tersedia | `_iter_form_downloads()` | `backend/api/storage.py` |
| Kirim katalog form ke AI | `_available_form_catalog()` | `backend/api/storage.py` |
| Map form pilihan AI | `_selected_form_downloads()` | `backend/api/storage.py` |
| Render block form | `renderFormDownloads()` | `frontend/web/assets/app.js` |
| Buka modal isi form | `openFormFillModal()` | `frontend/web/assets/app.js` |
| Submit form fill | `submitFormFill()` | `frontend/web/assets/app.js` |
| Endpoint scan field | `form_fields()` | `backend/api/routes_public.py` |
| Endpoint fill form | `fill_form()` | `backend/api/routes_public.py` |
| Resolve form path | `_resolve_form_path()` | `backend/api/forms_service.py` |
| Scan field workbook | `_scan_form_fields()` | `backend/api/forms_service.py` |
| Fill placeholder workbook | `_fill_form_placeholders()` | `backend/api/forms_service.py` |

### Cara field Excel dideteksi

| Rule | Detail |
|---|---|
| Placeholder valid | Cell yang seluruh isinya bracket, contoh `[  ]` atau `[Tanggal]` |
| Label field | Diambil dari isi bracket, cell kiri, atau cell atas lewat `_field_label()` |
| Field yang ditampilkan | Blok isian awal yang contiguous; bagian bawah seperti signature/free text dilewati |
| Deduplicate | Label sama hanya muncul sekali di modal, tapi saat fill semua placeholder dengan label itu ikut terisi |
| Security | `_resolve_form_path()` memastikan path ada di `DATA_DIR`, file `.xlsx`, dan `document_kind=form` |

## Index Lokasi Cepat

| Kebutuhan cek | Mulai dari |
|---|---|
| Kenapa jawaban chat berubah topik | `backend/researcher_crew/src/researcher_crew/main.py` |
| Kenapa retrieval tidak nemu sumber | `backend/preprocessing/vectorstore.py` |
| Kenapa form muncul/tidak muncul | `backend/api/storage.py` |
| Kenapa admin harus rebuild | `backend/api/routes_admin.py` dan `backend/preprocessing/ingest.py` |
| Kenapa FAQ gagal dibuat | `backend/api/faq_service.py` |
| Kenapa field form tidak muncul | `backend/api/forms_service.py` |
| Kenapa form filled download gagal | `backend/api/forms_service.py` dan `backend/api/routes_public.py` |
