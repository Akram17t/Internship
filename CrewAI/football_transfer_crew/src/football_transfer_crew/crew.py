import os

from crewai import Agent, Crew, LLM, Process, Task
from crewai.agents.agent_builder.base_agent import BaseAgent
from crewai.project import CrewBase, agent, crew, task

from football_transfer_crew.tools.playersearch import PlayerSearchTool


shared_llm = LLM(
    model=os.getenv("MODEL", "ollama/llama3.1"),
    api_base=os.getenv("API_BASE", "http://localhost:11434"),
    temperature=0.2,
)


@CrewBase
class FootballTransferCrew:
    """Football transfer recommendation crew."""

    agents: list[BaseAgent]
    tasks: list[Task]

    agents_config = "config/agents.yaml"
    tasks_config = "config/tasks.yaml"

    @agent
    def transfer_scout(self) -> Agent:
        return Agent(
            config=self.agents_config["transfer_scout"],  # type: ignore[index]
            tools=[PlayerSearchTool()],
            llm=shared_llm,
            verbose=True,
        )

    @agent
    def report_writer(self) -> Agent:
        return Agent(
            config=self.agents_config["report_writer"],  # type: ignore[index]
            llm=shared_llm,
            verbose=True,
        )

    @task
    def find_best_transfer(self) -> Task:
        return Task(
            config=self.tasks_config["find_best_transfer"],  # type: ignore[index]
        )

    @task
    def generate_transfer_report(self) -> Task:
        return Task(
            config=self.tasks_config["generate_transfer_report"],  # type: ignore[index]
            context=[self.find_best_transfer()],
        )

    @crew
    def crew(self) -> Crew:
        return Crew(
            agents=self.agents,
            tasks=self.tasks,
            process=Process.sequential,
            verbose=True,
        )
