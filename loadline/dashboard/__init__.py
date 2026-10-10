"""Web dashboard: v3-design run pages rendered from run artifacts."""

from loadline.dashboard.render import render_run_page
from loadline.dashboard.server import serve

__all__ = ["render_run_page", "serve"]
