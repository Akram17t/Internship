# Backend Topology - ICS SOP & Knowledge Assistant

Topologi komponen backend dan alur data utama: chat, semantic cache, FAQ,
ingestion, flowchart extraction, dan document reindex.

```mermaid
flowchart TB
    Browser["Browser UI"]
    Ollama["Ollama<br/>LLM + embedding + vision"]
    Reranker["CrossEncoder<br/>reranker"]

    subgraph API["FastAPI - backend/api"]
        direction TB
        Chat["routes_public.py<br/>/query"]
        FlowchartAPI["routes_public.py<br/>/api/flowcharts/{id}"]
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

    Browser -->|HTTP| API
    Chat --> CacheStore
    CacheStore --> CacheDB
    Chat --> Main
    Chat --> FlowchartAPI
    FlowchartAPI --> FlowchartCache

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

- **Chat**: `/query` mengambil conversation context, rewrite follow-up bila perlu, cek semantic cache, lalu hanya menjalankan retrieval + CrewAI/Ollama jika cache miss.
- **Semantic cache**: payload jawaban ada di `app_state.db`; embedding pertanyaan ada di `backend/cache/semantic_chroma`; cache di-reset setelah reindex.
- **FAQ**: admin membuat FAQ lewat retrieval + Ollama direct, lalu hasil valid disimpan ke `faqs.json`.
- **Ingestion**: dokumen di `backend/data/` dimuat, flowchart PDF diekstrak bila enabled, teks di-chunk per section, lalu vector DB SOP dibangun ulang.
- **Flowchart**: hasil vision disimpan ke `backend/cache/flowcharts`; screenshot hanya dikirim ke chat jika `FLOWCHART_DISPLAY_ENABLED=true`.
- **Reindex**: upload/update/delete SOP menandai `requires_reindex`; rebuild embeddings membangun index baru dan menghapus semantic cache lama.

Penjelasan per-file detail ada di [BACKEND_FLOW.md](BACKEND_FLOW.md) dan
alur runtime cepat ada di [SYSTEM_FLOWS.md](SYSTEM_FLOWS.md).
