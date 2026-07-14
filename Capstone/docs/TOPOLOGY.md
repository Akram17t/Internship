# Backend Topology - ICS SOP & Knowledge Assistant

Topologi komponen utama aplikasi: chat RAG, semantic cache, FAQ, ingestion,
flowchart extraction, document reindex, dan PDF form editor schema-driven.

```mermaid
flowchart TB
    Browser["Browser UI<br/>static vanilla JS"]
    FrontendModules["frontend/web/assets/js<br/>chat + faq + library + forms + drafts"]
    Ollama["Ollama<br/>LLM + embedding + vision"]
    Reranker["CrossEncoder<br/>reranker"]

    subgraph API["FastAPI - backend/api"]
        direction TB
        Chat["routes_public.py<br/>/query"]
        FlowchartAPI["routes_public.py<br/>/api/flowcharts/{id}"]
        FormSchemaAPI["routes_public.py<br/>/api/forms/schema + /api/forms/fields"]
        FormFillAPI["routes_public.py<br/>/api/forms/fill"]
        Faq["routes_admin.py<br/>/api/admin/faq"]
        DocMgmt["routes_admin.py<br/>document upload/delete/reindex"]
    end

    subgraph State["State and cache"]
        direction TB
        CacheStore["cache_store.py<br/>conversation + FAQ/admin JSON helpers"]
        CacheDB[("app_state.db<br/>conversation_messages<br/>semantic_cache_entries")]
        SemanticCache["semantic_cache.py<br/>exact + vector answer cache"]
        SemanticChroma[("semantic_chroma<br/>question vectors")]
        FlowchartCache[("cache/flowcharts<br/>vision JSON payloads")]
        Faqs[("faqs.json")]
    end

    subgraph FormSystem["Form system"]
        direction TB
        FormSvc["forms_service.py<br/>schema loader + legacy placeholder fill + schema render"]
        FormSchemas[/"backend/form_schemas<br/>template schemas"/]
    end

    subgraph Crew["researcher_crew"]
        direction TB
        Main["main.py<br/>rewrite, cache lookup, generate"]
        Retrieve["custom_tool.py<br/>retrieve_knowledge"]
        CrewDef["crew.py + config<br/>CrewAI chat answer"]
    end

    subgraph Prep["preprocessing"]
        direction LR
        Loader["loader.py"] --> FlowExt["flowchart_extractor.py"] --> Chunker["chunker.py"]
        Loader --> Chunker
        Chunker --> Embed["embedding.py"] --> VStore["vectorstore.py"]
    end

    Data[/"backend/data<br/>SOP + forms"/]
    Chroma[("backend/chroma_db<br/>SOP vector indexes")]

    Browser --> FrontendModules
    FrontendModules -->|HTTP| API
    Chat --> CacheStore
    CacheStore --> CacheDB
    Chat --> Main
    Chat --> FlowchartAPI
    Browser --> FormSchemaAPI
    Browser --> FormFillAPI
    FlowchartAPI --> FlowchartCache
    FormSchemaAPI --> FormSvc
    FormFillAPI --> FormSvc
    FormSvc --> FormSchemas
    FormSvc --> Data

    Main --> SemanticCache
    SemanticCache --> CacheDB
    SemanticCache --> SemanticChroma
    Main --> Retrieve
    Main --> CrewDef
    Main --> Ollama
    CrewDef --> Ollama
    Retrieve --> VStore
    VStore --> Chroma
    VStore --> Reranker

    Faq --> Main
    Faq --> Faqs

    DocMgmt --> Data
    DocMgmt --> Prep
    Data --> Loader
    FlowExt --> Ollama
    FlowExt --> FlowchartCache
    Embed --> Ollama
    VStore --> Chroma
    Prep --> SemanticCache
```

## Alur Ringkas

- **Frontend**: `frontend/web/assets/app.js` hanya bootstrap state/navigasi; logic utama dipisah ke `assets/js/chat.js`, `forms.js`, `faq.js`, `library.js`, `auth.js`, `storage.js`, `drafts.js`, dan `markdown.js`.
- **Chat**: `/query` mengambil conversation context, rewrite follow-up bila perlu, cek semantic cache, lalu hanya menjalankan retrieval + CrewAI/Ollama jika cache miss.
- **Semantic cache**: payload jawaban ada di `app_state.db`; embedding pertanyaan ada di `backend/cache/semantic_chroma`; cache di-reset setelah reindex.
- **FAQ**: admin membuat FAQ lewat retrieval + Ollama direct, lalu hasil valid disimpan ke `faqs.json`.
- **Form editor PDF**: `assets/js/forms.js` mengambil `GET /api/forms/schema` untuk template yang sudah dimigrasikan, menampilkan preview PDF di client, lalu submit `multipart/form-data` ke `POST /api/forms/fill`. `forms_service.py` merender text, textarea, checkbox, dan signature image langsung ke PDF di memory.
- **Draft form lokal**: `assets/js/storage.js` menyimpan draft field form ke `localStorage`; `assets/js/drafts.js` menampilkan launcher draft di chat supaya user bisa melanjutkan form yang belum selesai.
- **Form fallback lama**: jika schema belum tersedia, frontend masih bisa pakai `GET /api/forms/fields` dan `POST /api/forms/fill` dengan mode placeholder-scan sederhana.
- **Ingestion**: dokumen di `backend/data/` dimuat, flowchart PDF diekstrak bila enabled, teks di-chunk per section, lalu vector DB SOP dibangun ulang.
- **Flowchart**: hasil vision disimpan ke `backend/cache/flowcharts`; screenshot hanya dikirim ke chat jika `FLOWCHART_DISPLAY_ENABLED=true`.
- **Reindex**: upload/update/delete SOP menandai `requires_reindex`; rebuild embeddings membangun index baru dan menghapus semantic cache lama.

Penjelasan per-file detail ada di [BACKEND_FLOW.md](BACKEND_FLOW.md) dan
alur runtime cepat ada di [SYSTEM_FLOWS.md](SYSTEM_FLOWS.md).
