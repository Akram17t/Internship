# Football Transfer Crew

CrewAI project for scouting football transfer targets from a local player dataset and generating a short transfer report.

## What It Does

- asks for a club, target position, and budget
- searches `data/players.csv` for suitable players
- recommends the best transfer target plus alternatives
- generates a board-ready transfer report in `transfer_report.md`

## Model Setup

This project is configured for Ollama with Llama 3.1 through `.env`:

```env
MODEL=ollama/llama3.1
API_BASE=http://localhost:11434
```

Before running the crew, make sure Ollama is available locally:

```bash
ollama pull llama3.1
ollama serve
```

## Run

From the project root:

```bash
crewai run
```

The app will prompt you for:

- club name
- needed position
- budget in million euros

You can also skip the prompts and pass values directly:

```bash
uv run run_crew --club Arsenal --position CM --budget 75 --no-prompt
```

## Project Structure

- `src/football_transfer_crew/crew.py`: builds the agents, tasks, tool, and LLM setup
- `src/football_transfer_crew/main.py`: handles CLI input, interactive prompts, and crew execution
- `src/football_transfer_crew/tools/playersearch.py`: searches the local player database
- `src/football_transfer_crew/config/agents.yaml`: reference copy of the manual agent setup
- `src/football_transfer_crew/config/tasks.yaml`: reference copy of the manual task setup
- `data/players.csv`: scouting dataset used by the search tool

## Notes

- `crew.py` now builds agents and tasks manually, not from YAML decorators
- the player search tool now lives in a single file: `playersearch.py`
