"""Entry point: python main.py"""

from __future__ import annotations

from maestro_common import settings
from maestro_common.server import build_app, configure_logging, serve
from maestro_common.skills import load_skills

from server import build_mcp, health_check_for


def create_app():
    configure_logging()
    mcp, domain = build_mcp()
    skills = load_skills(settings.agent_skills, settings.skills_dir)
    return build_app(mcp, health=health_check_for(domain, skills))


if __name__ == "__main__":
    serve(create_app(), port=8000)
