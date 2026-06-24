from pathlib import Path

from langchain_chroma import Chroma
from langchain_ollama import OllamaEmbeddings, OllamaLLM


BASE_DIR = Path(__file__).resolve().parent.parent
CHROMA_DIR = BASE_DIR / "chroma_db"

EMBED_MODEL = "nomic-embed-text"
LLM_MODEL = "llama3.1"
TOP_K = 5
FALLBACK_ANSWER = "I could not find that information."


def build_rag() -> tuple[Chroma, OllamaLLM]:
    if not CHROMA_DIR.exists():
        raise FileNotFoundError(
            f"Chroma database not found: {CHROMA_DIR}. Run ingest.py first."
        )

    embeddings = OllamaEmbeddings(model=EMBED_MODEL)

    db = Chroma(
        persist_directory=str(CHROMA_DIR),
        embedding_function=embeddings,
    )

    llm = OllamaLLM(model=LLM_MODEL)

    return db, llm


def build_prompt(question: str, context: str) -> str:
    return f"""
You are answering questions about company documents.

Use the context below to answer the question.

You may summarize information from the context.

If the answer is not present at all in the context,
say "I could not find that information.""

Context:
{context}

Question:
{question}

Answer:
""".strip()


def ask(question: str) -> dict[str, list[str] | str]:
    cleaned_question = question.strip()
    if not cleaned_question:
        raise ValueError("Question must not be empty.")

    db, llm = build_rag()
    docs = db.similarity_search(cleaned_question, k=TOP_K)

    if not docs:
        return {
            "answer": FALLBACK_ANSWER,
            "sources": [],
        }

    context = "\n\n".join(doc.page_content for doc in docs)
    prompt = build_prompt(cleaned_question, context)
    print("\n===== CONTEXT =====")
    print(context)
    print("===================\n")
    answer = llm.invoke(prompt)

    sources = sorted(
        {
            Path(doc.metadata.get("source", "unknown")).name
            for doc in docs
        }
    )

    return {
        "answer": answer,
        "sources": sources,
    }


def main() -> None:
    print("Simple RAG")
    print("Type 'exit' to quit.\n")

    while True:
        question = input("Question: ").strip()

        if question.lower() == "exit":
            break

        if not question:
            print("Please enter a question.\n")
            continue

        try:
            result = ask(question)
        except Exception as error:
            print(f"\nERROR:\n{error}\n")
            print("=" * 50 + "\n")
            continue

        print("\nANSWER:")
        print(result["answer"])

        print("\nSOURCES:")
        if result["sources"]:
            for source in result["sources"]:
                print(f"- {source}")
        else:
            print("- No sources found")

        print("\n" + "=" * 50 + "\n")


if __name__ == "__main__":
    main()
