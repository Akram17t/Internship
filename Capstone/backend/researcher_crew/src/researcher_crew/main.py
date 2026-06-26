#!/usr/bin/env python
from __future__ import annotations

import sys
import warnings

from datetime import datetime

from researcher_crew.crew import ResearcherCrew

warnings.filterwarnings("ignore", category=SyntaxWarning, module="pysbd")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def run_knowledge_crew(question: str) -> str:
    """
    Run the crew for a single user question and return the final answer text.
    """
    inputs = {
        "question": question,
        "current_year": str(datetime.now().year),
    }
    result = ResearcherCrew().crew().kickoff(inputs=inputs)
    return str(result)


def run():
    """
    Run the crew.
    """
    inputs = {
        "question": "What does the knowledge base say about AI LLMs?",
        "current_year": str(datetime.now().year),
    }

    try:
        ResearcherCrew().crew().kickoff(inputs=inputs)
    except Exception as e:
        raise Exception(f"An error occurred while running the crew: {e}")


def train():
    """
    Train the crew for a given number of iterations.
    """
    inputs = {
        "question": "What does the knowledge base say about AI LLMs?",
        "current_year": str(datetime.now().year),
    }
    try:
        ResearcherCrew().crew().train(n_iterations=int(sys.argv[1]), filename=sys.argv[2], inputs=inputs)

    except Exception as e:
        raise Exception(f"An error occurred while training the crew: {e}")

def replay():
    """
    Replay the crew execution from a specific task.
    """
    try:
        ResearcherCrew().crew().replay(task_id=sys.argv[1])

    except Exception as e:
        raise Exception(f"An error occurred while replaying the crew: {e}")

def test():
    """
    Test the crew execution and returns the results.
    """
    inputs = {
        "question": "What does the knowledge base say about AI LLMs?",
        "current_year": str(datetime.now().year)
    }

    try:
        ResearcherCrew().crew().test(n_iterations=int(sys.argv[1]), eval_llm=sys.argv[2], inputs=inputs)

    except Exception as e:
        raise Exception(f"An error occurred while testing the crew: {e}")

def run_with_trigger():
    """
    Run the crew with trigger payload.
    """
    import json

    if len(sys.argv) < 2:
        raise Exception("No trigger payload provided. Please provide JSON payload as argument.")

    try:
        trigger_payload = json.loads(sys.argv[1])
    except json.JSONDecodeError:
        raise Exception("Invalid JSON payload provided as argument")

    inputs = {
        "crewai_trigger_payload": trigger_payload,
        "question": "",
        "current_year": ""
    }

    try:
        result = ResearcherCrew().crew().kickoff(inputs=inputs)
        return result
    except Exception as e:
        raise Exception(f"An error occurred while running the crew with trigger: {e}")
