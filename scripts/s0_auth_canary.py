#!/usr/bin/env python3
"""S-AUTH spike: one live OpenRouter call (run manually; see docs/testing-and-model.md)."""

from __future__ import annotations

import asyncio
import os
import sys

from pydantic import BaseModel
from pydantic_ai import Agent
from pydantic_ai.models.openrouter import OpenRouterModel


class CanaryOut(BaseModel):
    answer: str


async def main() -> int:
    if not os.environ.get("OPENROUTER_API_KEY"):
        print("OPENROUTER_API_KEY missing", file=sys.stderr)
        return 2
    model_id = os.environ.get("LOADLINE_MODEL", "openrouter:deepseek/deepseek-v4.1-flash")
    if model_id.startswith("openrouter:"):
        model_id = model_id.split(":", 1)[1]
    agent = Agent(OpenRouterModel(model_id), output_type=CanaryOut)

    @agent.tool_plain
    def add(a: int, b: int) -> int:
        return a + b

    result = await agent.run("Use the add tool to compute 2+2, then return answer as string '4'.")
    print(result.output)
    print("usage:", result.usage())
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
