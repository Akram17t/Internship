# Backend Topology — ICS SOP & Knowledge Assistant

Topologi komponen backend dan alur data utama (chat, FAQ, ingestion). Render
otomatis di GitHub atau VS Code (ekstensi *Markdown Preview Mermaid*).

```mermaid
flowchart TB
    Browser["🌐 Browser — UI"]
    Ollama["🤖 Ollama<br/>LLM + embedding"]
    Reranker["CrossEncoder<br/>reranker"]

    subgraph API["⚙️ FastAPI · api/main.py"]
        direction TB
        Chat["Chat — /query"]
        Faq["FAQ — /api/admin/faq"]
        DocMgmt["Dokumen & reindex"]
    end

    subgraph Crew["🧠 researcher_crew"]
        direction TB
        Main["main.py<br/>rewrite · generate"]
        Retrieve["custom_tool<br/>retrieve_knowledge"]
        CrewDef["crew.py + config<br/>CrewAI (chat)"]
    end

    subgraph Prep["📥 preprocessing"]
        direction LR
        Loader["loader"] --> Chunker["chunker"] --> Embed["embedding"] --> VStore["vectorstore"]
    end

    Chroma[("💾 ChromaDB<br/>index vektor")]
    Conv[("💾 conversations.json")]
    Faqs[("💾 faqs.json")]
    Data[/"📄 data/ — dokumen sumber"/]

    Browser -->|HTTP| API

    Chat -->|run_knowledge_crew| Main
    Faq -->|run_faq_crew| Main
    Chat -->|riwayat| Conv
    Faq -->|simpan| Faqs
    DocMgmt --> Prep
    DocMgmt --> Data

    Main -->|retrieve| Retrieve
    Main -->|chat: CrewAI| CrewDef
    Main -->|rewrite + FAQ gen| Ollama
    CrewDef -->|kickoff| Ollama
    Retrieve -->|hybrid_search| VStore
    VStore --> Chroma
    VStore -->|rerank| Reranker

    Loader -->|baca| Data
    Embed -->|embed| Ollama
    VStore -->|tulis index| Chroma

    classDef ext fill:#e7f0fb,stroke:#2f6fb0,color:#12365e;
    classDef api fill:#fdeaea,stroke:#c0392b,color:#7b1f16;
    classDef crew fill:#efe7fb,stroke:#7b4fb0,color:#3d2560;
    classDef ing fill:#e7f6ec,stroke:#3a9d5d,color:#1d5233;
    classDef store fill:#fbf3e0,stroke:#c79a2e,color:#6b5111;

    class Browser,Ollama,Reranker ext;
    class Chat,Faq,DocMgmt api;
    class Main,Retrieve,CrewDef crew;
    class Loader,Chunker,Embed,VStore ing;
    class Chroma,Conv,Faqs,Data store;
```

## Legenda

| Warna | Komponen |
|---|---|
| 🔵 Biru | Eksternal — Browser, Ollama, Reranker |
| 🔴 Merah | FastAPI (`api/main.py`) — chat, FAQ, dokumen |
| 🟣 Ungu | RAG orchestration (`researcher_crew`) |
| 🟢 Hijau | Pipeline ingestion (`preprocessing`) |
| 🟡 Kuning | Penyimpanan — ChromaDB, cache, dokumen |

## Alur ringkas

- **Chat**: `/query` → `main.py` → rewrite (Ollama) → retrieve (`custom_tool` → `vectorstore` → ChromaDB + reranker) → generate lewat **CrewAI** → simpan riwayat.
- **FAQ**: `/api/admin/faq` → `main.py` → retrieve → generate **Ollama langsung** → simpan ke `faqs.json`.
- **Ingestion**: dokumen di `data/` → loader → chunker → embedding (Ollama) → vectorstore → tulis index ke ChromaDB.

Penjelasan per-file detail ada di [BACKEND_FLOW.md](BACKEND_FLOW.md).
