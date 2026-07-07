# Backend Reference — ICS SOP & Knowledge Assistant

Dokumentasi menyeluruh backend: tiap file penting, fungsi-fungsinya, dan alur
program dari awal sampai response. Frontend tidak dibahas. Semua path relatif ke
folder `Capstone/`.

---

## Gambaran umum

Aplikasi RAG lokal untuk dokumen SOP/HR internal. FastAPI menyajikan REST API
sekaligus menghosting UI. Dokumen di-ingest menjadi vektor di ChromaDB, lalu
pertanyaan dijawab dengan mengambil potongan dokumen relevan dan menyusun jawaban
melalui Ollama (LLM lokal). Dua jalur jawaban: **chat** (lewat CrewAI) dan **FAQ**
(lewat Ollama langsung).

Komponen utama:

| Lapisan | Folder/File | Peran |
|---|---|---|
| Config | `backend/settings.py` | Loader `.env` + helper env |
| API + host UI | `backend/api/main.py` | Semua endpoint REST, serve frontend |
| Ingestion | `backend/preprocessing/` | Dokumen → chunk → embedding → ChromaDB |
| Startup check | `backend/scripts/storage_status.py` | Validasi vector DB / dokumen |
| Orkestrasi RAG | `backend/researcher_crew/` | Retrieval + generation (chat & FAQ) |
| Penyimpanan | `backend/cache/`, `backend/chroma_db/`, `backend/data/` | Cache percakapan/FAQ, index vektor, dokumen sumber |

Stack: FastAPI · Uvicorn · CrewAI · LangChain (loader/splitter/chroma/ollama) ·
ChromaDB · Ollama (LLM + embedding) · sentence-transformers (reranker) · pypdf ·
docx2txt.

---

## 1. Konfigurasi bersama — `backend/settings.py`

Dipakai hampir semua modul untuk membaca `.env`.

- `load_capstone_env()` — muat `.env` dari root `Capstone/` sekali saja (idempotent, pakai flag `_ENV_LOADED`).
- `get_required_env(name)` — ambil env; error kalau kosong.
- `get_env(name, default)` — ambil env string dengan default.
- `get_int_env(name, default)` — versi integer.
- `get_float_env(name, default)` — versi float.
- Konstanta `ROOT_DIR` — path root `Capstone/`.

Variabel `.env` utama: `MODEL`, `EMBED_MODEL`, `RERANK_MODEL`, `OLLAMA_BASE_URL`,
`OLLAMA_NUM_CTX`, `OLLAMA_NUM_PREDICT`, `FAQ_NUM_PREDICT`, `OLLAMA_TIMEOUT_SECONDS`,
`RETRIEVAL_MIN_SCORE`, `TOP_K`, `CHROMA_DIR`, `DATA_DIR`.

---

## 2. Startup — `run.bat` & `storage_status.py`

### `run.bat`
Titik masuk di Windows:
1. Pastikan venv `backend\researcher_crew\.venv` + dependency siap.
2. Baca `CHROMA_DIR` / `DATA_DIR` dari `.env`.
3. Jalankan `storage_status` untuk cek kesiapan penyimpanan.
4. Kalau vector DB belum valid tapi ada dokumen sumber → jalankan ingestion (`python -m backend.preprocessing.ingest`).
5. Cari port bebas, jalankan `uvicorn backend.api.main:app`, buka browser.
6. `clean.bat` — hentikan server, bersihkan cache Python (`__pycache__`, `.pytest_cache`, `*.pyc`), dan hapus seluruh isi `CHROMA_DIR` (kecuali `.gitkeep`) sehingga run berikutnya melakukan ingestion ulang.

### `backend/scripts/storage_status.py`
Cek startup berbasis exit code:
- `has_valid_vector_db()` — `CHROMA_DIR` ada, punya penanda index aktif `.active-chroma-index`, index yang ditunjuk ada, dan ada marker skema `.citation-metadata-v1`.
- `has_source_documents()` — ada file `.pdf/.docx/.txt` di `DATA_DIR`.
- `_resolve_env_path(name, default)` — resolusi path env relatif ke `ROOT_DIR`.
- `main()` — argumen `vector-db` / `source-docs` → exit 0 (valid) / 1 (tidak).

---

## 3. Ingestion pipeline — `backend/preprocessing/`

Dijalankan dari CLI (`python -m backend.preprocessing.ingest`) atau endpoint
`POST /api/admin/reindex`. Urutan: **ingest → loader → chunker → embedding → vectorstore**.

### `ingest.py`
- `main()` — orkestrasi: `load_documents` → `chunk_documents` → `rebuild_vectorstore`, lalu tulis marker `.citation-metadata-v1` di folder index aktif, dan cetak ringkasan.
- `get_data_dir()` — resolusi `DATA_DIR`.
- Konstanta `CITATION_SCHEMA_MARKER` = `.citation-metadata-v1`.

### `loader.py`
- `load_documents(data_dir)` — scan rekursif, ambil `.pdf/.docx/.txt`, gabung jadi list `Document`.
- `_load_single_document(path)` — pilih loader LangChain: `PyPDFLoader` (PDF), `Docx2txtLoader` (DOCX), `TextLoader` (TXT).
- `_normalize_documents(docs, path)` — set metadata: `source`, `doc_type`, `document_kind`, `title`, `page`.
- `classify_document_kind(path)` — `form` (xlsx / nama diawali "form"), `sop` (diawali "sop"), atau `document`.
- Konstanta `SUPPORTED_EXTENSIONS`.

### `chunker.py`
- `chunk_documents(documents)` — jalankan `split_documents_by_section`, potong tiap section dengan splitter, beri `chunk_id` berurutan.
- `split_documents_by_section(documents)` — pisah dokumen per heading, simpan `metadata["section"]`, jaga metadata halaman.
- `_clean_page_text(document)` — buang noise SOP berulang (header/footer, "Nomor Dokumen", "X dari Y", lembar pengesahan/histori) dan baris judul yang berulang.
- `_looks_like_heading(line)` — deteksi heading via pola `Pasal N`, `BAB N`, heading bernomor (`4.1 ...`), atau huruf besar pendek.
- `_append_segment(...)` — tambahkan segmen konten ke hasil dengan metadata section.
- `build_text_splitter(chunk_size=1200, chunk_overlap=150)` — `RecursiveCharacterTextSplitter`.
- `_normalize_whitespace`, `_is_noise_line` — util. Pola disimpan di `NOISE_LINE_PATTERNS`, `ARTICLE/CHAPTER/NUMBERED/UPPERCASE_HEADING_PATTERN`, `SKIP_PAGE_MARKERS`.

### `embedding.py`
- `get_embedding_model()` — `OllamaEmbeddings(model=EMBED_MODEL, base_url=OLLAMA_BASE_URL)`.

### `vectorstore.py`
- `rebuild_vectorstore(chunks)` — buat index Chroma baru di `indexes/<uuid>`, tulis `.active-chroma-index` menunjuk ke situ (index lama tidak ditimpa).
- `get_chroma_dir()` — resolusi folder index aktif dari penanda; validasi agar tetap di dalam `CHROMA_DIR`.
- `get_vectorstore()` — buka Chroma pada index aktif dengan embedding.
- `get_reranker()` — muat `CrossEncoder` (`RERANK_MODEL`) jika `sentence-transformers` tersedia; else `None` (cache via `lru_cache`).
- `_rerank_documents(query, documents)` — skor ulang kandidat, normalisasi ke 0–1 (sigmoid), urutkan; return list `(document, score)`.
- `hybrid_search(query, k=4)` — ambil kandidat via `similarity_search` (`RERANK_CANDIDATES`), rerank, buang yang skornya < `RETRIEVAL_MIN_SCORE`, kembalikan top-`k` `Document`.
- Konstanta `ACTIVE_INDEX_FILE`, `VERSIONED_INDEX_DIR`.

---

## 4. API layer — `backend/api/main.py`

Modul FastAPI. Saat di-import: `load_capstone_env()`, tambahkan `researcher_crew/src`
ke `sys.path`, buat `app`, siapkan konstanta & lock. `researcher_crew.main` di-import
**lazy** (di dalam fungsi endpoint). Endpoint UI/aset di-mount di akhir modul.

### Konstanta penting
`EMBEDDABLE_EXTENSIONS` (`.pdf/.docx/.txt`), `LIBRARY_EXTENSIONS` (+`.xlsx`),
`MAX_DOCUMENT_BYTES` (25 MB), batas percakapan
(`MAX_CONVERSATIONS`, `MAX_CONVERSATION_TURNS`, `MAX_CONVERSATION_CONTEXT_CHARS`,
`CONVERSATION_TTL`), lock (`CONVERSATION_LOCK`, `FAQ_LOCK`, `REINDEX_LOCK`), dan
admin config (`backend/cache/admin.json`), dan pinned FAQ organogram.

### Model Pydantic (kontrak request/response)
`QueryRequest`, `CitationResponse`, `FormDownloadResponse`, `QueryResponse`,
`FAQItem`, `AdminFAQPayload`, `AdminFAQResponse`, `LibraryItem`,
`AdminDocumentPayload`, `AdminDocumentResponse`, `AdminReindexResponse`.

### Helper — dokumen & library
- `_get_data_dir()` — resolusi `DATA_DIR`.
- `_document_kind_for_path(path)` — `form` / `sop` / `document`.
- `_is_embeddable_path(path)` — apakah bisa masuk index (pdf/docx/txt).
- `_to_library_item(path, data_dir)` / `_iter_library_items()` — bangun daftar item library.
- `_resolve_document_path(document_path)` — resolusi + cegah path traversal ke luar `DATA_DIR`.
- `_decode_document(content_base64)` — decode base64 upload, validasi ukuran/kosong.

### Helper — form download
- `_format_form_display_name(path)` — rapikan nama form untuk ditampilkan.
- `_form_download_response(path, data_dir)` — bentuk `FormDownloadResponse`.
- `_iter_form_downloads()` / `_iter_form_paths()` — kumpulkan file `.xlsx` yang tersedia.
- `_available_form_catalog(forms)` — kirim katalog form ke AI.
- `_selected_form_downloads(selected_names, forms)` — map pilihan form dari AI ke `FormDownloadResponse`.

### Helper — percakapan (cache)
- `_get_cache_dir()`, `_get_conversation_file()`, `_get_faq_file()` — path cache.
- `_clean_conversation_id(value)` — sanitasi/validasi id, atau buat UUID baru.
- `_parse_conversation_timestamp(value)` — parse ISO timestamp.
- `_prune_expired_conversations(...)` — buang percakapan lewat `CONVERSATION_TTL`.
- `_load_conversations()` / `_save_conversations(...)` — baca/tulis `conversations.json` (dengan prune + batasi jumlah/percakapan).
- `_get_conversation_context(conversation_id)` — susun riwayat jadi teks `User: ... / Assistant: ...` (dibatasi `MAX_CONVERSATION_CONTEXT_CHARS`).
- `_append_conversation_turn(id, question, answer)` — tambahkan pasangan turn baru + timestamp.

### Helper — citation & FAQ
- `_citation_download_url(source)` — URL unduh dari nama sumber.
- `_normalize_citation(raw, index)` / `_normalize_citations(item)` — rapikan citation (dari list, atau fallback dari `source`).
- `_normalize_faq_item(item)` — validasi & lengkapi FAQ item (isi source/URL dari citation bila kosong).
- `_load_faqs()` / `_save_faqs(items)` — baca/tulis `faqs.json` (kosong bila file belum ada).
- `_find_faq_index(items, id)` — cari index FAQ (404 kalau tak ada).
- `_is_unusable_faq_answer(answer, citations)` — jawaban dianggap tak layak bila tanpa citation atau mengandung frasa penolakan.
- `_build_faq_item(payload, faq_id=None)` — panggil `run_faq_crew`, bentuk `FAQItem`, tolak (422) bila tak layak.
- `_require_admin(x_admin_email)` — cek email admin (403 kalau bukan).

### Endpoint

| Method + Path | Fungsi | Keterangan |
|---|---|---|
| `GET /health` | `health_check` | Status |
| `POST /query` | `query_knowledge_base` | Chat (lihat §6) |
| `GET /api/faq` | `get_faq` | List FAQ |
| `POST /api/admin/faq` | `create_faq` | Buat FAQ (admin) |
| `PUT /api/admin/faq/{id}` | `update_faq` | Regenerate FAQ (admin) |
| `DELETE /api/admin/faq/{id}` | `delete_faq` | Hapus FAQ (admin) |
| `GET /api/library` | `get_library` | List dokumen (admin) |
| `POST /api/admin/documents` | `save_document` | Upload/replace dokumen (admin) |
| `DELETE /api/admin/documents/{path}` | `delete_document` | Hapus dokumen (admin) |
| `POST /api/admin/reindex` | `reindex_documents` | Rebuild embeddings (admin, pakai `REINDEX_LOCK`) |
| `GET /api/documents/{path}` | `download_document` | Unduh (form: publik, lainnya: admin) |
| `GET /` | `frontend_app` | Serve `index.html` |

---

## 5. Orkestrasi RAG — `backend/researcher_crew/`

### `src/researcher_crew/main.py`
Otak retrieval + generation.
- `run_knowledge_crew(question, conversation_context="")` — jalur chat: rewrite query → retrieval → generation (CrewAI) → rapikan citation.
- `run_faq_crew(question)` — jalur FAQ: retrieval → generation (Ollama langsung) → rapikan citation.
- `_rewrite_query(question, conversation_context)` — ubah follow-up jadi pertanyaan mandiri via LLM (fallback ke pertanyaan asli bila tak ada konteks / gagal).
- `_generate_answer(question, evidence)` — jalankan `ResearcherCrew().crew().kickoff(...)`.
- `_generate_faq_answer(question, evidence)` — susun prompt FAQ singkat, panggil Ollama.
- `_ollama_generate(prompt, num_predict, temperature, seed)` — helper Ollama (nonaktifkan reasoning tersembunyi, retry aman untuk model yang tak mendukung).
- `_post_ollama_generate(payload)` — HTTP `POST /api/generate` via `urllib`.
- `_ollama_model_name()`, `_ollama_base_url()`, `_read_ollama_error(err)` — util Ollama.
- `_crew_output_to_text(result)` — ambil teks dari hasil CrewAI.
- `OllamaGenerationError` — exception generation.
- `GENERATED_SOURCES_SECTION` — regex pembersih section "Sumber/Referensi" yang kadang ditulis LLM.

### `src/researcher_crew/tools/custom_tool.py`
- `retrieve_knowledge(query, k=None)` — panggil `hybrid_search`, susun **evidence** (`[n] File | Section | PDF page` + kutipan) dan daftar **citations** (id, source, page, section, chunk_id) dengan dedup per (source, page, section).
- `_citation_from_document(document, id)` — bentuk satu entri citation.

### `src/researcher_crew/crew.py`
Definisi CrewAI (pola `CrewBase`):
- `_llm(temperature, max_tokens)` — buat `crewai.LLM` yang menunjuk Ollama (`MODEL`, `OLLAMA_BASE_URL`, timeout, seed).
- `answer_writer()` — agent (config dari `agents.yaml`).
- `chat_answer_task()` — task (config dari `tasks.yaml`).
- `crew()` — rakit agent + task jadi Crew (`Process.sequential`); `kickoff(inputs)` mengisi placeholder lalu memanggil Ollama.

### `src/researcher_crew/config/`
- `agents.yaml` → `answer_writer`: role/goal/backstory (persona jawaban chat).
- `tasks.yaml` → `chat_answer_task`: instruksi + placeholder `{question}`, `{evidence}`, aturan sitasi & reliability.

---

## 6. Alur CHAT (end-to-end)

`POST /query` → `query_knowledge_base(payload)`:
```
1. conversation_id      = _clean_conversation_id(payload.conversation_id)
2. conversation_context = _get_conversation_context(conversation_id)
3. available_forms = _iter_form_downloads()
4. answer, raw_citations, selected_form_names = run_knowledge_crew(payload.question, conversation_context, available_forms=_available_form_catalog(available_forms))
5. _append_conversation_turn(conversation_id, question, answer)
6. citations      = [CitationResponse(... + download_url)]
7. form_downloads = _selected_form_downloads(selected_form_names, available_forms) bila answer supported
8. return QueryResponse(answer, citations, form_downloads, conversation_id)
```

`run_knowledge_crew`:
```
a. standalone_question = _rewrite_query(question, conversation_context)
b. evidence, citations = retrieve_knowledge(standalone_question)   # custom_tool → hybrid_search
c. if not citations: return "tidak tersedia" (tanpa LLM)
d. answer = _generate_answer(standalone_question, evidence)        # crew.py → CrewAI → Ollama
e. bersihkan section sumber, normalkan marker [n], filter citation yang benar dipakai
f. return answer, citations
```

Rangkaian modul: `api/main.py` → `researcher_crew/main.py` → `tools/custom_tool.py`
→ `preprocessing/vectorstore.py` (retrieval) → `crew.py` + `config/*.yaml` (generation)
→ balik ke `api/main.py` untuk membentuk response.

---

## 7. Alur FAQ (end-to-end)

`POST /api/admin/faq` → `create_faq` → `_build_faq_item(payload)`:
```
1. answer, raw_citations = run_faq_crew(question)
2. citations = [CitationResponse(... + download_url)]
3. if _is_unusable_faq_answer(answer, citations): raise 422
4. return FAQItem  → items.append → _save_faqs() (faqs.json)
```

`run_faq_crew`:
```
a. evidence, citations = retrieve_knowledge(question)   # tanpa rewrite (tidak ada riwayat)
b. if not citations: return "belum tersedia"
c. answer = _generate_faq_answer(question, evidence)    # Ollama langsung via _ollama_generate
d. bersihkan marker & filter citation
```

`PUT /api/admin/faq/{id}` (regenerate) dan `DELETE` mengikuti pola serupa lewat
`_build_faq_item` / `_find_faq_index` dengan `FAQ_LOCK`.

---

## 8. Alur dokumen & reindex

- `POST /api/admin/documents` → `save_document` — validasi ekstensi & ukuran, decode base64, tulis ke `DATA_DIR` (mode insert atau replace). `requires_reindex=true` bila file embeddable.
- `DELETE /api/admin/documents/{path}` → `delete_document` — hapus file, tandai perlu reindex bila embeddable.
- `POST /api/admin/reindex` → `reindex_documents` — panggil `backend.preprocessing.ingest.main()` (bangun index Chroma baru), dilindungi `REINDEX_LOCK`.
- `GET /api/documents/{path}` → `download_document` — dokumen "form" publik; jenis lain butuh header admin.

---

## 9. Penyimpanan

| Lokasi | Isi |
|---|---|
| `backend/data/` | Dokumen sumber (PDF/DOCX/TXT untuk di-embed, XLSX form untuk diunduh) |
| `backend/chroma_db/` | Index vektor ChromaDB (folder ber-UUID + penanda index aktif) |
| `backend/cache/conversations.json` | Riwayat percakapan (untuk konteks rewrite); auto-prune per TTL |
| `backend/cache/faqs.json` | FAQ tersimpan |

---

## 10. Ringkasan fungsi per file

| File | Fungsi kunci |
|---|---|
| `settings.py` | `load_capstone_env`, `get_env`, `get_required_env`, `get_int_env`, `get_float_env` |
| `scripts/storage_status.py` | `has_valid_vector_db`, `has_source_documents`, `main` |
| `preprocessing/ingest.py` | `main`, `get_data_dir` |
| `preprocessing/loader.py` | `load_documents`, `_load_single_document`, `_normalize_documents`, `classify_document_kind` |
| `preprocessing/chunker.py` | `chunk_documents`, `split_documents_by_section`, `_clean_page_text`, `_looks_like_heading`, `build_text_splitter` |
| `preprocessing/embedding.py` | `get_embedding_model` |
| `preprocessing/vectorstore.py` | `rebuild_vectorstore`, `hybrid_search`, `_rerank_documents`, `get_vectorstore`, `get_chroma_dir`, `get_reranker` |
| `api/main.py` | `query_knowledge_base`, `create/update/delete_faq`, `_build_faq_item`, `_selected_form_downloads`, konversi conversation/citation/faq/document, endpoint dokumen & reindex |
| `researcher_crew/main.py` | `run_knowledge_crew`, `run_faq_crew`, `_rewrite_query`, `_generate_answer`, `_generate_faq_answer`, `_ollama_generate`, `_post_ollama_generate` |
| `researcher_crew/tools/custom_tool.py` | `retrieve_knowledge` |
| `researcher_crew/crew.py` | `_llm`, `answer_writer`, `chat_answer_task`, `crew` |
| `researcher_crew/config/agents.yaml` | `answer_writer` (persona) |
| `researcher_crew/config/tasks.yaml` | `chat_answer_task` (instruksi) |
