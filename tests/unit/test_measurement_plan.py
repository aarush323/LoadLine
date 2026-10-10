from loadline.core.measurement_plan import build_measurement_plan

MIX = [
    {
        "weight": 50,
        "op": {
            "id": "a",
            "service": "web",
            "port": 8000,
            "selector": {"method": "GET", "path": "/a"},
        },
    },
    {
        "weight": 50,
        "op": {
            "id": "b",
            "service": "web",
            "port": 8000,
            "selector": {"method": "GET", "path": "/b"},
        },
    },
]


def test_rate_step_honors_params_shape():
    plan = build_measurement_plan(
        "rate_step",
        {"rate": 12, "warmup": 2, "duration": 8},
        MIX,
        fast=False,
    )
    assert plan is not None
    assert plan["shape"] == {"rate": 12, "warmup": 2, "duration": 8}
    assert len(plan["mix"]) == 2


def test_isolate_filters_mix_to_one_operation():
    plan = build_measurement_plan("isolate", {"operation_id": "b"}, MIX)
    assert plan is not None
    assert len(plan["mix"]) == 1
    assert plan["mix"][0]["op"]["id"] == "b"


def test_warm_cold_extends_warmup():
    plan = build_measurement_plan("warm_cold", {"cold_factor": 3}, MIX, fast=True)
    assert plan is not None
    assert plan["shape"]["warmup"] == 15
