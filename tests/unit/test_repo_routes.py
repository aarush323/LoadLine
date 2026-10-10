import json
from pathlib import Path
from unittest.mock import MagicMock

from loadline.core.ledger import Ledger
from loadline.entire_runtime.graph import GraphOutput
from loadline.investigator.deps import InvestigationDeps
from loadline.investigator.repo_routes import discover_routes


def test_discover_routes_from_handles_route_ndjson(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "openapi.json").write_text(json.dumps({"paths": {"/health": {"get": {}}}}))

    graph = MagicMock()
    graph.capabilities.return_value = {"supported_relation_types": ["CALLS", "HANDLES_ROUTE"]}
    graph.edges_supports_worktree.return_value = True
    graph.run.return_value = GraphOutput(
        args=["edges"],
        text='',
        ok=True,
        records=[
            {
                "relation": "HANDLES_ROUTE",
                "method": "GET",
                "path": "/health",
                "symbol": "health",
                "file": "app.py",
                "line": 3,
            }
        ],
    )

    run_dir = tmp_path / "run"
    run_dir.mkdir()
    deps = InvestigationDeps(
        repo_root=repo,
        run_dir=run_dir,
        run_id="r1",
        ledger=Ledger.open(run_dir, "r1"),
        graph=graph,
        dirty_worktree=False,
    )
    out = discover_routes(deps)
    assert out["count"] >= 1
    health = next(r for r in out["routes"] if r["path"] == "/health")
    assert health["handler"] == "health"
    assert health["source"] == "HANDLES_ROUTE"
    assert out["exhaustive"] is True
