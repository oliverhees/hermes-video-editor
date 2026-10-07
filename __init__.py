"""hermes-video-editor: local FFmpeg video editing tools for Hermes Agent."""
from __future__ import annotations

from pathlib import Path

SKILL_NAME = "video-editor"


def register(ctx) -> None:
    from .schemas import TOOLS

    for tool in TOOLS:
        ctx.register_tool(name=tool["name"], toolset=tool["toolset"],
                          schema=tool["schema"], handler=tool["handler"])
    skill = Path(__file__).resolve().parent / "skills" / SKILL_NAME / "SKILL.md"
    if skill.is_file():
        ctx.register_skill(SKILL_NAME, skill)
