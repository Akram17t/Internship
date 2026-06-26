from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from crewai import Agent, Crew, LLM, Process, Task
from dotenv import load_dotenv

from backend.crewai.tools.rag_tool import RAGSearchTool

load_dotenv()


BASE_DIR = Path(__file__).resolve().parent


def _load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        return yaml.safe_load(file)


def _build_llm() -> LLM:
    return LLM(
        model=os.getenv("MODEL", "ollama/llama3.1"),
        api_base=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
        temperature=0.1,
    )


class ICSKnowledgeCrew:
    def __init__(self) -> None:
        self.llm = _build_llm()
        self.scout_config = _load_yaml(BASE_DIR / "agents" / "scout.yaml")
        self.explainer_config = _load_yaml(BASE_DIR / "agents" / "explainer.yaml")
        self.retrieve_task_config = _load_yaml(BASE_DIR / "tasks" / "retrieve_task.yaml")
        self.answer_task_config = _load_yaml(BASE_DIR / "tasks" / "answer_task.yaml")

    def scout_agent(self) -> Agent:
        return Agent(
            role=self.scout_config["role"],
            goal=self.scout_config["goal"],
            backstory=self.scout_config["backstory"],
            llm=self.llm,
            tools=[RAGSearchTool()],
            verbose=True,
        )

    def explainer_agent(self) -> Agent:
        return Agent(
            role=self.explainer_config["role"],
            goal=self.explainer_config["goal"],
            backstory=self.explainer_config["backstory"],
            llm=self.llm,
            verbose=True,
        )

    def retrieve_task(self, scout: Agent) -> Task:
        return Task(
            description=self.retrieve_task_config["description"],
            expected_output=self.retrieve_task_config["expected_output"],
            agent=scout,
        )

    def answer_task(self, explainer: Agent, context_task: Task) -> Task:
        return Task(
            description=self.answer_task_config["description"],
            expected_output=self.answer_task_config["expected_output"],
            agent=explainer,
            context=[context_task],
            markdown=True,
        )

    def build(self) -> Crew:
        scout = self.scout_agent()
        explainer = self.explainer_agent()
        retrieve = self.retrieve_task(scout)
        answer = self.answer_task(explainer, retrieve)

        return Crew(
            agents=[scout, explainer],
            tasks=[retrieve, answer],
            process=Process.sequential,
            verbose=True,
        )

    def run(self, question: str):
        return self.build().kickoff(inputs={"question": question})


def run_knowledge_crew(question: str) -> str:
    result = ICSKnowledgeCrew().run(question)
    raw_output = getattr(result, "raw", None)
    if isinstance(raw_output, str) and raw_output.strip():
        return raw_output.strip()
    return str(result).strip()
