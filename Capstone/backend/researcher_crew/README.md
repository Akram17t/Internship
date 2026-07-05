# Researcher Crew

CrewAI package used by the Capstone FastAPI application to turn retrieved policy evidence into grounded chat and FAQ answers.

The web application enters through `run_knowledge_crew(question)` and `run_faq_crew(question)` in `src/researcher_crew/main.py`. Retrieval runs before the crew, then a purpose-specific writer agent produces the grounded answer:

1. `answer_writer` writes chat answers with citation markers.
2. `faq_writer` writes short FAQ answers with citation markers.

Run the complete application from the Capstone root with `run.bat`. This package does not expose a separate CrewAI CLI entry point.
