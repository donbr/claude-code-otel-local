from pathlib import Path

import pytest

from tests.offline.collector_graph import COMBOS, graph_errors, merge_configs

COLLECTOR = Path(__file__).resolve().parents[2] / "collector"


@pytest.mark.parametrize("o1,o2", COMBOS, ids=lambda x: x)
def test_every_combination_forms_a_valid_graph(o1, o2):
    cfg = merge_configs([COLLECTOR / "base.yaml", COLLECTOR / f"{o1}.yaml", COLLECTOR / f"{o2}.yaml"])
    assert graph_errors(cfg) == []


def test_openobserve_overlay_keeps_fanout_receivers():
    cfg = merge_configs([COLLECTOR / "base.yaml", COLLECTOR / "openobserve.yaml"])
    for p in ("metrics/out", "logs/out"):
        pipe = cfg["service"]["pipelines"][p]
        assert pipe["receivers"], p
        assert "otlphttp/openobserve" in pipe["exporters"], p
        assert any(e.startswith("file/") for e in pipe["exporters"]), p


def test_traces_go_to_phoenix_and_file_in_every_combo():
    for o1, o2 in COMBOS:
        cfg = merge_configs([COLLECTOR / "base.yaml", COLLECTOR / f"{o1}.yaml", COLLECTOR / f"{o2}.yaml"])
        pipes = cfg["service"]["pipelines"]
        assert set(pipes["traces/out"]["exporters"]) == {"file/traces", "forward/phoenix"}
        assert pipes["traces/phoenix"]["receivers"] == ["forward/phoenix"]
        assert pipes["traces/phoenix"]["exporters"] == ["otlphttp/phoenix"]


def test_openinference_mapping_runs_only_on_the_phoenix_branch():
    """traces.jsonl is the audit copy: the mapping must not run before the file exporter."""
    cfg = merge_configs([COLLECTOR / "base.yaml", COLLECTOR / "dual-env.yaml", COLLECTOR / "openobserve.yaml"])
    for name, pipe in cfg["service"]["pipelines"].items():
        has_mapping = "transform/openinference" in (pipe.get("processors") or [])
        assert has_mapping == (name == "traces/phoenix"), name


def test_every_env_pipeline_tags_the_environment():
    cfg = merge_configs([COLLECTOR / "base.yaml", COLLECTOR / "dual-env.yaml"])
    for name, pipe in cfg["service"]["pipelines"].items():
        if name.endswith(("/a", "/b")):
            procs = pipe["processors"]
            assert any(p.startswith("resource/") for p in procs), name
            if name.startswith("traces/"):
                assert any(p.startswith("attributes/") for p in procs), name


def test_graph_errors_catches_undefined_component():
    bad = {"receivers": {"otlp/a": {}}, "exporters": {}, "service": {"pipelines": {
        "traces/a": {"receivers": ["otlp/a"], "exporters": ["missing"]}}}}
    assert graph_errors(bad)
