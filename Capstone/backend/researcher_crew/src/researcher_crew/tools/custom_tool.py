from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Type

from crewai.tools import BaseTool
from dotenv import load_dotenv
from pydantic import BaseModel, Field

PROJECT_ROOT = Path(__file__).resolve().parents[5]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.preprocessing.vectorstore import similarity_search

load_dotenv()


class RAGSearchToolInput(BaseModel):
    """Input schema for the local RAG search tool."""

    query: str = Field(..., description="Question or search query to retrieve relevant knowledge chunks.")


class RAGSearchTool(BaseTool):
    name: str = "local_knowledge_search"
    description: str = (
        "Searches the local Chroma knowledge base and returns the most relevant document chunks "
        "with source metadata for answering internal ICS questions."
    )
    args_schema: Type[BaseModel] = RAGSearchToolInput

    def _run(self, query: str) -> str:
        top_k = int(os.getenv("TOP_K", "4"))
        documents = similarity_search(query, k=top_k)
        if not documents:
            return "No matching knowledge chunks were found in the local vector database."

        sections: list[str] = []
        for index, document in enumerate(documents, start=1):
            source = document.metadata.get("source", "unknown source")
            page = document.metadata.get("page")
            page_text = f", page {page + 1}" if isinstance(page, int) else ""
            content = " ".join(document.page_content.split())
            sections.append(f"{index}. Source: {source}{page_text}\n{content}")

        return "\n\n".join(sections)
