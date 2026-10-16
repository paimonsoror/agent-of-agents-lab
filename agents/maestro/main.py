"""Entry point: python main.py"""

from __future__ import annotations

from maestro_common.server import configure_logging, serve

from app import create_app

if __name__ == "__main__":
    configure_logging()
    serve(create_app(), port=8000)
