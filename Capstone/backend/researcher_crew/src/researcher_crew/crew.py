from __future__ import annotations

import sys
from pathlib import Path

from crewai import Agent, Crew, LLM, Process, Task
from crewai.agents.agent_builder.base_agent import BaseAgent
from crewai.project import CrewBase, agent, crew, task

PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.settings import get_int_env, get_required_env, load_capstone_env

load_capstone_env()


@CrewBase
class ResearcherCrew():
    """ResearcherCrew crew"""

    agents_config = "config/agents.yaml"
    tasks_config = "config/tasks.yaml"

    agents: list[BaseAgent]
    tasks: list[Task]

    def _llm(self, temperature: float = 0.2, max_tokens: int | None = None) -> LLM:
        return LLM(
            model=get_required_env("MODEL"),
            base_url=get_required_env("OLLAMA_BASE_URL"),
            temperature=temperature,
            max_tokens=max_tokens or get_int_env("OLLAMA_NUM_PREDICT", 1100),
            timeout=get_int_env("OLLAMA_TIMEOUT_SECONDS", 240),
            seed=7,
        )

    @agent
    def answer_writer(self) -> Agent:
        return Agent(
            config=self.agents_config["answer_writer"],  # type: ignore[index]
            llm=self._llm(temperature=0.3),
            verbose=False,
        )

    @agent
    def faq_writer(self) -> Agent:
        return Agent(
            config=self.agents_config["faq_writer"],  # type: ignore[index]
            llm=self._llm(
                temperature=0.1,
                max_tokens=get_int_env("FAQ_NUM_PREDICT", 180),
            ),
            verbose=False,
        )

    @task
    def chat_answer_task(self) -> Task:
        return Task(
            config=self.tasks_config["chat_answer_task"],  # type: ignore[index]
        )

    @task
    def faq_answer_task(self) -> Task:
        return Task(
            config=self.tasks_config["faq_answer_task"],  # type: ignore[index]
        )

    @crew
    def crew(self) -> Crew:
        """Creates the chat answer crew."""
        return Crew(
            agents=[self.answer_writer()],
            tasks=[self.chat_answer_task()],
            process=Process.sequential,
            verbose=False,
        )

    def faq_crew(self) -> Crew:
        """Creates the short FAQ answer crew."""
        return Crew(
            agents=[self.faq_writer()],
            tasks=[self.faq_answer_task()],
            process=Process.sequential,
            verbose=False,
        )
