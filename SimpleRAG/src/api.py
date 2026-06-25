from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from rag import ask


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1)


app = FastAPI(title="SimpleRAG API", version="1.0.0")


@app.get("/")
def root() -> dict[str, str]:
    return {"status": "running"}


@app.post("/ask")
def ask_endpoint(payload: AskRequest) -> dict:
    try:
        return ask(payload.question)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error)) from error
