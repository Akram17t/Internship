from __future__ import annotations

import os
from typing import Type

from crewai.tools import BaseTool
from dotenv import load_dotenv
from pydantic import BaseModel, Field

from backend.preprocessing.vectorstore import similarity_search

load_dotenv()


class RAGSearchToolInput(BaseModel):
    query: str = Field(..., description="User question to search in the internal knowledge base.")


class RAGSearchTool(BaseTool):
    name: str = "RAG Knowledge Search"
    description: str = (
        "Searches the internal SOP knowledge base and returns the most relevant chunks "
        "with document citations."
    )
    args_schema: Type[BaseModel] = RAGSearchToolInput

    def _format_result(self, index: int, content: str, source: str, page: str | int) -> str:
        return f"[Chunk {index}] Source: {source} | Page: {page}\n{content.strip()}"

    def _run(self, query: str) -> str:
        top_k = int(os.getenv("TOP_K", "4"))
        documents = similarity_search(query=query, k=top_k)

        if not documents:
            return "No relevant context found in the knowledge base."

        lines: list[str] = []
        for index, document in enumerate(documents, start=1):
            lines.append(
                self._format_result(
                    index=index,
                    content=document.page_content,
                    source=str(document.metadata.get("source", "unknown")),
                    page=document.metadata.get("page", "N/A"),
                )
            )

        return "\n\n".join(lines)
