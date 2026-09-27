"""Replicate the collector's multi --config merge (maps deep-merge, lists replace) and check the graph."""

from pathlib import Path

import yaml

COMBOS = [("none", "none"), ("dual-env", "none"), ("openobserve", "none"), ("dual-env", "openobserve")]
KINDS = ("receivers", "processors", "exporters", "connectors")


def _merge(a, b):
    if isinstance(a, dict) and isinstance(b, dict):
        out = dict(a)
        for k, v in b.items():
            out[k] = _merge(a[k], v) if k in a else v
        return out
    return b


def merge_configs(paths: list[Path]) -> dict:
    cfg: dict = {}
    for p in paths:
        cfg = _merge(cfg, yaml.safe_load(p.read_text()) or {})
    return cfg


def graph_errors(cfg: dict) -> list[str]:
    errors = []
    connectors = set(cfg.get("connectors") or {})
    pipelines = (cfg.get("service") or {}).get("pipelines") or {}
    if not pipelines:
        return ["no pipelines"]
    for name, pipe in pipelines.items():
        for role, kinds in (("receivers", ("receivers", "connectors")),
                            ("processors", ("processors",)),
                            ("exporters", ("exporters", "connectors"))):
            refs = pipe.get(role) or []
            if role != "processors" and not refs:
                errors.append(f"{name}: no {role}")
            for ref in refs:
                if not any(ref in (cfg.get(k) or {}) for k in kinds):
                    errors.append(f"{name}: undefined {role[:-1]} {ref}")
    for c in connectors:
        used_in = sum(c in (p.get("exporters") or []) for p in pipelines.values())
        used_out = sum(c in (p.get("receivers") or []) for p in pipelines.values())
        if not (used_in and used_out):
            errors.append(f"connector {c} must be both an exporter and a receiver")
    return errors
