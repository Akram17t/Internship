# Backend Topology - ICS SOP & Knowledge Assistant

Topologi komponen utama aplikasi: chat RAG, semantic cache, FAQ, ingestion,
flowchart extraction, document reindex, dan download template form PDF/DOCX.

```mermaid
flowchart TB
    Browser["Browser UI<br/>static vanilla JS"]
    FrontendModules["frontend/web/assets/js<br/>chat + faq + library + auth"]
    Ollama["Ollama<br/>LLM + embedding + vision"]
    Reranker["CrossEncoder<br/>reranker"]

    subgraph API["FastAPI - backend/api"]
        Chat["routes_public.py<br/>/query"]
        Downloads["routes_public.py<br/>/api/documents/{path}"]
        FlowchartAPI["routes_public.py<br/>/api/flowcharts/{id}"]
        Faq["routes_admin.py<br/>/api/admin/faq"]
        DocMgmt["routes_admin.py<br/>document upload/delete/reindex"]
    end

    subgraph State["State and cache"]
        CacheStore["cache_store.py<br/>conversation + FAQ/admin JSON helpers"]
        CacheDB[("app_state.db")]
        SemanticCache["semantic_cache.py<br/>exact + vector answer cache"]
        SemanticChroma[("semantic_chroma")]
        FlowchartCache[("cache/flowcharts")]
        Faqs[("faqs.json")]
    end

    subgraph Forms["Template forms"]
        FormSvc["forms_service.py<br/>PDF to DOCX sidecar"]
        Data[/"backend/data<br/>SOP + form PDF/DOCX"/]
    end

    subgraph RagRuntime["researcher_crew"]
        Main["main.py<br/>rewrite, cache lookup, generate"]
        Retrieve["custom_tool.py<br/>retrieve_knowledge"]
    end

    subgraph Prep["preprocessing"]
        Loader["loader.py"] --> FlowExt["flowchart_extractor.py"] --> Chunker["chunker.py"]
        Loader --> Chunker
        Chunker --> Embed["embedding.py"] --> VStore["vectorstore.py"]
    end

    Chroma[("backend/chroma_db")]

    Browser --> FrontendModules
    FrontendModules --> API
    Chat --> CacheStore
    CacheStore --> CacheDB
    Chat --> Main
    Chat --> FlowchartAPI
    Downloads --> FormSvc
    FlowchartAPI --> FlowchartCache
    FormSvc --> Data
    Main --> SemanticCache
    SemanticCache --> CacheDB
    SemanticCache --> SemanticChroma
    Main --> Retrieve
    Main --> Ollama
    Retrieve --> VStore
    VStore --> Chroma
    VStore --> Reranker
    Faq --> Main
    Faq --> Faqs
    DocMgmt --> Data
    DocMgmt --> FormSvc
    DocMgmt --> Prep
    Data --> Loader
    FlowExt --> Ollama
    FlowExt --> FlowchartCache
    Embed --> Ollama
    Prep --> SemanticCache
```

## Alur Ringkas

- **Frontend**: `app.js` bootstrap state/navigasi; logic utama ada di `chat.js`, `faq.js`, `library.js`, `auth.js`, `api.js`, dan `markdown.js`.
- **Chat**: `/query` mengambil context percakapan, cek semantic cache, retrieval jika cache miss, lalu mengembalikan jawaban, citation, form download, dan flowchart.
- **Form template**: form hanya diunduh sebagai template kosong. Browser membuka modal pilihan format, lalu memanggil `/api/documents/{path}` untuk PDF atau `?format=docx` untuk Word.
- **DOCX sidecar**: saat admin insert/update PDF form, `forms_service.py` membuat file `.docx` pasangan di `backend/data`. Saat PDF form dihapus, pasangan DOCX ikut dihapus.
- **Ingestion**: dokumen non-form di `backend/data/` dimuat, flowchart diekstrak bila enabled, teks di-chunk, lalu vector DB dibangun ulang.
- **Reindex**: upload/update/delete SOP menandai `requires_reindex`; rebuild embeddings membangun index baru dan menghapus semantic cache lama.
