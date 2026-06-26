from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel, Field

from backend.crewai.crew import run_knowledge_crew


app = FastAPI(title="ICS Knowledge Assistant API", version="1.0.0")


class QueryRequest(BaseModel):
    question: str = Field(..., min_length=3, description="Natural language question from the user.")


class QueryResponse(BaseModel):
    answer: str


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/query", response_model=QueryResponse)
def query_knowledge_base(payload: QueryRequest) -> QueryResponse:
    answer = run_knowledge_crew(payload.question)
    return QueryResponse(answer=answer)
