# ICS SOP & Knowledge Assistant - Architecture

Backend memakai API layer kecil: `backend/api/main.py` hanya mengekspor `app`
dan mengimpor route agar endpoint terdaftar.

## Topology

```mermaid
flowchart TB
    subgraph Client["Browser SPA"]
        UI["Vanilla JS UI"]
        CHATUI["assets/js/chat.js<br/>chat, citations, flowcharts, form links"]
        ADMINUI["assets/js/faq.js + library.js + auth.js<br/>FAQ, docs, admin"]
    end

    subgraph Server["FastAPI API layer"]
        MAIN["backend/api/main.py"]
        PUBLIC["routes_public.py<br/>chat, FAQ publik, download, root"]
        ADMIN["routes_admin.py<br/>login, FAQ admin, library, docs, reindex"]
        CORE["core.py<br/>app, konstanta, lock, assets"]
    end

    subgraph Services["API services"]
        STORAGE["storage.py<br/>dokumen, library, form catalog"]
        FORMSVC["forms_service.py<br/>DOCX sidecar template"]
        CACHE["cache_store.py<br/>conversation state, FAQ, admin.json"]
        STATE["cache_db.py<br/>SQLite state"]
        SEMCACHE["semantic_cache.py<br/>answer cache"]
        AUTH["auth.py<br/>token admin"]
        FAQSVC["faq_service.py<br/>build FAQ, pinned FAQ"]
        FLOWSVC["flowchart_service.py<br/>flowchart screenshot lookup"]
        MODELS["models.py<br/>request/response schema"]
    end

    subgraph RAG["RAG orchestration"]
        RCMAIN["researcher_crew/main.py"]
        TOOL["tools/custom_tool.py"]
    end

    subgraph Retrieval["Retrieval"]
        VS["preprocessing/vectorstore.py"]
        CHROMA[("ChromaDB")]
        RERANK["CrossEncoder reranker"]
    end

    subgraph Ingest["Ingestion"]
        INGEST["preprocessing/ingest.py"]
        LOAD["loader.py"]
        CHUNK["chunker.py"]
        FLOWEXT["flowchart_extractor.py"]
        EMB["embedding.py"]
    end

    DATA[/"backend/data"/]
    CACHEFILES[/"backend/cache"/]
    OLLAMA["Ollama local"]

    UI --> CHATUI
    UI --> ADMINUI
    CHATUI --> MAIN
    ADMINUI --> MAIN
    MAIN --> PUBLIC
    MAIN --> ADMIN
    PUBLIC --> STORAGE
    PUBLIC --> FORMSVC
    PUBLIC --> CACHE
    PUBLIC --> FLOWSVC
    PUBLIC --> RCMAIN
    ADMIN --> STORAGE
    ADMIN --> FORMSVC
    ADMIN --> CACHE
    ADMIN --> AUTH
    ADMIN --> FAQSVC
    ADMIN --> INGEST
    CACHE --> STATE
    SEMCACHE --> STATE
    RCMAIN --> TOOL
    RCMAIN --> SEMCACHE
    TOOL --> VS
    RCMAIN --> OLLAMA
    VS --> CHROMA
    VS --> RERANK
    DATA --> LOAD --> FLOWEXT --> CHUNK --> EMB --> CHROMA
    LOAD --> CHUNK
    EMB --> OLLAMA
    FLOWEXT --> OLLAMA
    CACHE --> CACHEFILES
    STATE --> CACHEFILES
    FLOWSVC --> CACHEFILES
    FORMSVC --> DATA
```

## Komponen

| Layer | File | Tanggung jawab |
|---|---|---|
| Config | `backend/settings.py` | Load `.env` dan helper env |
| API core | `backend/api/core.py` | Objek `app`, konstanta, lock, mount assets |
| API models | `backend/api/models.py` | Schema Pydantic untuk chat, FAQ, library, admin, dan download form |
| Public routes | `backend/api/routes_public.py` | Chat, FAQ publik, download dokumen/template, flowchart, root UI |
| Admin routes | `backend/api/routes_admin.py` | Login admin, FAQ admin, library, upload/delete docs, reindex |
| Storage helpers | `backend/api/storage.py` | Dokumen, library, form catalog, path validation |
| Form helpers | `backend/api/forms_service.py` | Generate, ambil, dan hapus DOCX sidecar untuk PDF form |
| Cache helpers | `backend/api/cache_store.py` | Context percakapan, `faqs.json`, dan `admin.json` |
| Semantic cache | `backend/semantic_cache.py` | Exact/vector answer cache dan reset saat reindex |
| Flowchart helpers | `backend/api/flowchart_service.py` | Cari payload flowchart untuk citation dan serve screenshot |
| Frontend chat | `frontend/web/assets/js/chat.js` | Submit chat, render jawaban/citation/flowchart, dan render tombol form |
| Frontend library | `frontend/web/assets/js/library.js` | List dokumen, upload/update/delete, modal PDF/Word, dan rebuild embeddings |

## Jalur Utama

**Chat**

`chat.js` -> `POST /query` -> `routes_public.py` -> context/cache ->
`researcher_crew/main.py` -> retrieval/generation bila cache miss -> response
`answer + citations + form_downloads + flowcharts`.

**Template form**

`chat.js` atau `library.js` membuka modal pilihan format. PDF memakai
`GET /api/documents/{form.pdf}`. Word memakai
`GET /api/documents/{form.pdf}?format=docx`, lalu `forms_service.py` memastikan
file `.docx` pasangan tersedia di `backend/data`.

**Upload dokumen dan reindex**

`library.js` -> `POST /api/admin/documents` atau `DELETE /api/admin/documents/...`.
Untuk PDF form, backend membuat/menghapus DOCX sidecar dan tidak meminta reindex.
Untuk dokumen embeddable non-form, frontend meminta admin menjalankan
`POST /api/admin/reindex`.

**Flowchart**

Saat ingest PDF, `flowchart_extractor.py` mencari diagram, memanggil Ollama
vision, menyimpan payload ke cache, dan memasukkan representasi teks ke vector DB.
