import shutil
from pathlib import Path

from langchain_chroma import Chroma
from langchain_community.document_loaders import DirectoryLoader, TextLoader
from langchain_ollama import OllamaEmbeddings

from citations import chunk_documents_by_section


BASE_DIR = Path(__file__).resolve().parent.parent
DOCS_DIR = BASE_DIR / "docs"
CHROMA_DIR = BASE_DIR / "chroma_db"
EMBED_MODEL = "nomic-embed-text"


def main() -> None:
    if not DOCS_DIR.exists():
        raise FileNotFoundError(f"Docs directory not found: {DOCS_DIR}")

    loader = DirectoryLoader(
        str(DOCS_DIR),
        glob="**/*.txt",
        loader_cls=TextLoader,
        loader_kwargs={"encoding": "utf-8"},
        show_progress=True,
    )
    documents = loader.load()

    if not documents:
        raise ValueError(f"No .txt documents found in: {DOCS_DIR}")

    print(f"Loaded {len(documents)} documents from {DOCS_DIR}")

    chunks = chunk_documents_by_section(documents)

    print(f"Created {len(chunks)} chunks")

    embeddings = OllamaEmbeddings(model=EMBED_MODEL)

    if CHROMA_DIR.exists():
        try:
            shutil.rmtree(CHROMA_DIR)
        except PermissionError as error:
            raise RuntimeError(
                "Could not rebuild Chroma DB because the folder is locked. "
                "Stop any running SimpleRAG API or CLI process, then run ingest.py again."
            ) from error

    db = Chroma.from_documents(
        documents=chunks,
        embedding=embeddings,
        persist_directory=str(CHROMA_DIR),
    )

    print(f"Vector database saved to {CHROMA_DIR}")
    print("Ingestion complete.")


if __name__ == "__main__":
    main()
