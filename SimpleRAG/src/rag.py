from langchain_chroma import Chroma
from langchain_ollama import OllamaEmbeddings, OllamaLLM

from pathlib import Path

from citations import build_citations

BASE_DIR = Path(__file__).resolve().parent.parent
CHROMA_DIR = BASE_DIR / "chroma_db"

EMBED_MODEL = "nomic-embed-text"
LLM_MODEL = "llama3.1"
TOP_K = 5
MIN_RELEVANCE_SCORE = 0.5
MAX_CONTEXT_DOCS = 1
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

Answer only using the provided context.
Give one direct answer only.
Do not mention missing information if the context already contains the answer.
Do not offer alternatives, multiple options, or extra commentary.
If the question is explicitly yes/no, answer yes or no first, then explain briefly.
If the answer is not stated in the context, reply with exactly "{FALLBACK_ANSWER}".

Context:
{context}

Question:
{question}

Answer:
""".strip()


def ask(question: str, top_k: int = TOP_K) -> dict:
    cleaned_question = question.strip()
    if not cleaned_question:
        raise ValueError("Question must not be empty.")

    db, llm = build_rag()
    matches = db.similarity_search_with_relevance_scores(cleaned_question, k=top_k)
    docs = [
        doc for doc, score in matches
        if score >= MIN_RELEVANCE_SCORE
    ][:MAX_CONTEXT_DOCS]

    if not docs:
        return {
            "answer": FALLBACK_ANSWER,
            "citations": [],
        }

    context_parts = []
    for doc in docs:
        section = doc.metadata.get("section", "section unknown")
        source = doc.metadata.get("source", "unknown")
        context_parts.append(f"[{source} | {section}]\n{doc.page_content}")

    context = "\n\n".join(context_parts)
    prompt = build_prompt(cleaned_question, context)
    answer = llm.invoke(prompt)
    citations = build_citations(docs)

    return {
        "answer": answer,
        "citations": citations,
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

        print("\nCITATIONS:")
        if result["citations"]:
            for citation in result["citations"]:
                print(f"- {citation['source']} ({citation['section']})")
        else:
            print("- No citations found")

        print("\n" + "=" * 50 + "\n")


if __name__ == "__main__":
    main()
