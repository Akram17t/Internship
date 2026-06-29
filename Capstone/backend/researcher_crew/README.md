# Researcher Crew

CrewAI package used by the Capstone FastAPI application to turn retrieved policy evidence into a grounded answer.

The web application enters through `run_knowledge_crew(question)` in `src/researcher_crew/main.py`. Retrieval runs before the crew, then two agents execute sequentially:

1. `researcher` filters the supplied evidence.
2. `reporting_analyst` writes the Indonesian answer with citation markers.

Run the complete application from the Capstone root with `run.bat`. This package does not expose a separate CrewAI CLI entry point.
