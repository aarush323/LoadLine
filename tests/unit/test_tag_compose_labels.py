from loadline.adapters.runtime.docker_runner import tag_compose_labels


def test_run_label_on_map_labels():
    plan = {"services": {"web": {"image": "x", "labels": {"app": "1"}}}}
    out = tag_compose_labels(plan, "run123")
    assert out["services"]["web"]["labels"]["app"] == "1"
    assert out["services"]["web"]["labels"]["loadline.run"] == "run123"


def test_run_label_on_list_labels():
    plan = {
        "services": {
            "web": {
                "image": "x",
                "labels": ["ingress.enable=true", "loadline.run=old"],
            }
        }
    }
    out = tag_compose_labels(plan, "run456")
    labels = out["services"]["web"]["labels"]
    assert isinstance(labels, list)
    assert "ingress.enable=true" in labels
    assert "loadline.run=run456" in labels
    assert "loadline.run=old" not in labels


def test_run_label_when_labels_missing():
    plan = {"services": {"web": {"image": "x"}}}
    out = tag_compose_labels(plan, "run789")
    assert out["services"]["web"]["labels"] == {"loadline.run": "run789"}
