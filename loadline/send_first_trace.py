"""Send one hosted trace to finish Neatlogs onboarding (dashboard unlocks after this)."""

from __future__ import annotations

import os
import sys

import neatlogs
from dotenv import load_dotenv


def main() -> None:
    load_dotenv()
    api_key = (os.environ.get("NEATLOGS_API_KEY") or "").strip()
    if not api_key or api_key in {"<your-project-api-key>", "your-project-api-key"}:
        print(
            "NEATLOGS_API_KEY is missing in .env.\n\n"
            "You are not blocked on Settings — the key is on the SAME page that says\n"
            "'Send your first trace' / 'Connect your app below'. Scroll that page and\n"
            "look for 'Project API key', 'Copy API key', or a code snippet with the key.\n"
            "Paste it into .env as NEATLOGS_API_KEY=...\n\n"
            "Then run:  uv run send-first-trace\n"
            "Or:       uv run python -m neatlogs doctor --probe --json\n",
            file=sys.stderr,
        )
        raise SystemExit(1)

    endpoint = os.environ.get("NEATLOGS_ENDPOINT", "https://ingest.neatlogs.com").strip()
    neatlogs.init(api_key=api_key, endpoint=endpoint, workflow_name="first-trace")
    with neatlogs.trace("neatHack onboarding", kind="WORKFLOW"):
        with neatlogs.trace("hello", kind="TOOL"):
            pass
    neatlogs.flush()
    neatlogs.shutdown()
    print("Trace sent. Refresh app.neatlogs.com — onboarding should complete in a few seconds.")


if __name__ == "__main__":
    main()
