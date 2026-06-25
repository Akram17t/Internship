from __future__ import annotations

import csv
from functools import cached_property
from pathlib import Path
from typing import Type

from crewai.tools import BaseTool
from pydantic import BaseModel, Field


class PlayerSearchToolInput(BaseModel):
    position: str = Field(..., description="Target playing position, for example ST, CM, CB, or GK.")
    budget: float = Field(..., description="Maximum market value budget in million euros.")


class PlayerSearchTool(BaseTool):
    name: str = "Player Search Tool"
    description: str = (
        "Search football players from the local scouting dataset and return the best "
        "matches for a target position within a transfer budget."
    )
    args_schema: Type[BaseModel] = PlayerSearchToolInput

    @property
    def _data_path(self) -> Path:
        return Path(__file__).resolve().parents[3] / "data" / "players.csv"

    @cached_property
    def _available_positions(self) -> tuple[str, ...]:
        positions: set[str] = set()
        with self._data_path.open("r", encoding="utf-8", newline="") as csv_file:
            reader = csv.DictReader(csv_file)
            for row in reader:
                primary_position = row["position"].strip().upper()
                secondary_position = row["secondary_position"].strip().upper()

                if primary_position:
                    positions.add(primary_position)
                if secondary_position:
                    positions.add(secondary_position)

        return tuple(sorted(positions))

    def get_available_positions(self) -> list[str]:
        return list(self._available_positions)

    def is_valid_position(self, position: str) -> bool:
        return position.strip().upper() in self._available_positions

    def _run(self, position: str, budget: float) -> str:
        requested_position = position.strip().upper()
        max_budget = float(budget)

        matches: list[dict[str, str | float | int]] = []
        with self._data_path.open("r", encoding="utf-8", newline="") as csv_file:
            reader = csv.DictReader(csv_file)
            for row in reader:
                primary_position = row["position"].strip().upper()
                secondary_position = row["secondary_position"].strip().upper()
                market_value = float(row["market_value_million"])

                if requested_position not in {primary_position, secondary_position}:
                    continue

                if market_value > max_budget:
                    continue

                matches.append(
                    {
                        "name": row["name"],
                        "club": row["club"],
                        "position": row["position"],
                        "secondary_position": row["secondary_position"] or "-",
                        "market_value_million": market_value,
                        "overall_rating": int(float(row["overall_rating"])),
                        "potential": int(float(row["potential"])),
                        "age": int(float(row["age"])),
                        "play_style": row["play_style"],
                    }
                )

        if not matches:
            return (
                f"No players found for position {requested_position} within a budget "
                f"of {max_budget:.1f} million euros."
            )

        matches.sort(
            key=lambda player: (
                -int(player["overall_rating"]),
                -int(player["potential"]),
                float(player["market_value_million"]),
                int(player["age"]),
            )
        )

        lines = [
            f"Top transfer candidates for {requested_position} within {max_budget:.1f} million euros:",
        ]
        for index, player in enumerate(matches[:10], start=1):
            lines.append(
                (
                    f"{index}. {player['name']} | Club: {player['club']} | "
                    f"Position: {player['position']} ({player['secondary_position']}) | "
                    f"Value: EUR {float(player['market_value_million']):.1f}M | "
                    f"Rating: {player['overall_rating']} | Potential: {player['potential']} | "
                    f"Age: {player['age']} | Style: {player['play_style']}"
                )
            )

        return "\n".join(lines)


__all__ = ["PlayerSearchTool"]
