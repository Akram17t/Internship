# Backend Reference - ICS SOP & Knowledge Assistant

Dokumentasi ini menjelaskan file penting, responsibility tiap modul, dan alur
runtime utama.

## 1. Gambaran Umum

| Area | Folder/File | Peran |
|---|---|---|
| Config | `backend/settings.py` | Loader `.env` dan helper env |
| API layer | `backend/api/` | FastAPI app, route publik/admin, helper service |
| RAG layer | `backend/researcher_crew/` | Rewrite query, retrieval, generation chat dan FAQ |
| Preprocessing | `backend/preprocessing/` | Ingestion dokumen ke ChromaDB |
| State/cache | `backend/cache_db.py`, `backend/semantic_cache.py` | Conversation store, semantic cache, dan metadata state |

## 2. API Layer

| File | Isi utama |
|---|---|
| `core.py` | `app`, konstanta, lock, mount `/assets` |
| `models.py` | Schema chat, citation, form download, FAQ, admin, library, log |
| `storage.py` | `DATA_DIR`, library item, katalog form, path validation, decode upload |
| `forms_service.py` | Generate/ambil/hapus DOCX sidecar untuk PDF form |
| `routes_public.py` | `/health`, `/query`, `/api/faq`, `/api/flowcharts/{id}`, `/api/citations/{path}`, `/api/documents/{path}`, `/` |
| `routes_admin.py` | Login admin, FAQ admin, library, upload/delete docs, reindex, logs |

## 3. Chat Flow

```text
1. Bersihkan / buat conversation_id
2. Ambil context percakapan dari SQLite app_state.db
3. Kumpulkan katalog form PDF yang tersedia
4. Kirim question + context + katalog form ke run_knowledge_crew()
5. Rewrite follow-up jika perlu
6. Cek semantic cache memakai standalone question
7. Jika cache miss, retrieval Chroma + rerank lalu generate jawaban
8. Simpan semantic cache jika jawaban punya citation dan bukan fallback
9. Simpan turn baru ke app_state.db
10. Bentuk CitationResponse, form_downloads, dan flowcharts untuk frontend
```

## 4. Dokumen, Form Template, dan Reindex

### Upload / Replace

`POST /api/admin/documents`:
- validasi token admin
- validasi extension
- tolak upload form `.docx` sebagai dokumen utama
- decode base64
- insert file baru atau replace file lama
- jika file adalah PDF form, buat ulang pasangan `.docx`
- jika file embeddable non-form berubah, set `requires_reindex=True`

### Delete

`DELETE /api/admin/documents/{path}`:
- validasi token admin
- validasi path aman
- jika file adalah PDF form, hapus pasangan `.docx`
- hapus file
- tandai apakah butuh reindex

### Download form template

```text
PDF:  GET /api/documents/Form%20-%20X.pdf
DOCX: GET /api/documents/Form%20-%20X.pdf?format=docx
```

DOCX form tidak muncul sebagai item library terpisah. File tersebut adalah
sidecar dari PDF form dan dibuat oleh `forms_service.py`.

### Reindex

`POST /api/admin/reindex` memanggil `backend.preprocessing.ingest.main()`,
rebuild vectorstore dari dokumen terbaru, lalu menghapus semantic cache lama.
PDF form dan DOCX sidecar form tidak masuk embedding.

## 5. Semantic Cache

Semantic cache berjalan di dalam `run_knowledge_crew()`:

```text
1. Normalisasi standalone question
2. Exact lookup ke SQLite semantic_cache_entries
3. Jika exact miss, similarity lookup ke backend/cache/semantic_chroma
4. Validasi active_index, MODEL, EMBED_MODEL, citation, dan fallback status
5. Jika hit, return cached answer
6. Jika miss, lanjut RAG normal lalu store cache jika valid
```

## 6. FAQ Flow

```text
1. Admin kirim pertanyaan FAQ
2. routes_admin.py panggil _build_faq_item()
3. faq_service.py panggil run_faq_crew()
4. researcher_crew/main.py ambil evidence via retrieve_knowledge()
5. Jika tidak ada citation relevan, FAQ ditolak
6. Jika ada, Ollama buat jawaban FAQ singkat
7. FAQ disimpan ke faqs.json
```

## 7. Ingestion Layer

| File | Peran |
|---|---|
| `loader.py` | Load PDF, DOCX, TXT; skip file form dari embedding |
| `chunker.py` | Bersihkan noise SOP, split section, attach table context, chunk final |
| `flowchart_extractor.py` | Deteksi flowchart, panggil Ollama vision, cache payload |
| `embedding.py` | Buat `OllamaEmbeddings` |
| `vectorstore.py` | Rebuild/open Chroma, hybrid search, rerank |
| `ingest.py` | Orkestrasi load, chunk, rebuild vectorstore, reset semantic cache |

## 8. Penyimpanan

| Lokasi | Isi |
|---|---|
| `backend/data/` | Dokumen sumber, PDF form, dan DOCX sidecar form |
| `backend/chroma_db/` | ChromaDB + marker active index |
| `backend/cache/app_state.db` | Riwayat percakapan + semantic cache |
| `backend/cache/semantic_chroma` | Vector store untuk pertanyaan semantic cache |
| `backend/cache/flowcharts` | Cache JSON hasil ekstraksi flowchart |
| `backend/cache/faqs.json` | FAQ tersimpan |
| `backend/cache/admin.json` | Config admin lokal |
