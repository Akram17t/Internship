from __future__ import annotations

import os

from crewai import Agent, Crew, LLM, Process, Task
from crewai.project import CrewBase, agent, crew, task
from crewai.agents.agent_builder.base_agent import BaseAgent
from dotenv import load_dotenv

from researcher_crew.tools import RAGSearchTool

load_dotenv()


@CrewBase
class ResearcherCrew():
    """ResearcherCrew crew"""

    agents_config = "config/agents.yaml"
    tasks_config = "config/tasks.yaml"

    agents: list[BaseAgent]
    tasks: list[Task]

    def _llm(self) -> LLM:
        return LLM(
            model=os.getenv("MODEL", "ollama/llama3.1"),
            base_url=os.getenv("OLLAMA_BASE_URL", os.getenv("API_BASE", "http://localhost:11434")),
        )

    @agent
    def researcher(self) -> Agent:
        return Agent(
            config=self.agents_config['researcher'], # type: ignore[index]
            llm=self._llm(),
            tools=[RAGSearchTool()],
            verbose=True
        )

    @agent
    def reporting_analyst(self) -> Agent:
        return Agent(
            config=self.agents_config['reporting_analyst'], # type: ignore[index]
            llm=self._llm(),
            verbose=True
        )

    @task
    def research_task(self) -> Task:
        return Task(
            config=self.tasks_config['research_task'], # type: ignore[index]
        )

    @task
    def reporting_task(self) -> Task:
        return Task(
            config=self.tasks_config['reporting_task'], # type: ignore[index]
            context=[self.research_task()],
        )

    @crew
    def crew(self) -> Crew:
        """Creates the ResearcherCrew crew"""
        return Crew(
            agents=self.agents,
            tasks=self.tasks,
            process=Process.sequential,
            verbose=True,
        )
