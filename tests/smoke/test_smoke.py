import json
import time

import pytest

from tests.offline.collector_graph import COMBOS
from tests.smoke.otlp_send import send
from tests.smoke.stack import Stack

pytestmark = pytest.mark.docker


def jsonl_records(path, marker):
    """Return (resource_attrs, item_attrs) for every record whose attributes carry the marker."""
    found = []
    if not path.exists():
        return found
    for line in path.read_text().splitlines():
        batch = json.loads(line)
        for key, scope_key, items_key in (("resourceSpans", "scopeSpans", "spans"),
                                          ("resourceLogs", "scopeLogs", "logRecords"),
                                          ("resourceMetrics", "scopeMetrics", "metrics")):
            for res in batch.get(key, []):
                rattrs = {a["key"]: next(iter(a["value"].values())) for a in res["resource"].get("attributes", [])}
                for scope in res.get(scope_key, []):
                    for item in scope.get(items_key, []):
                        if marker in json.dumps(item):
                            attrs = {a["key"]: next(iter(a["value"].values())) for a in item.get("attributes", [])}
                            found.append((rattrs, attrs))
    return found


def wait_for(fn, timeout=60, interval=2):
    deadline = time.time() + timeout
    while time.time() < deadline:
        result = fn()
        if result:
            return result
        time.sleep(interval)
    return fn()


@pytest.mark.parametrize("o1,o2", COMBOS, ids=lambda x: x)
def test_stack_tags_and_routes_every_signal(o1, o2, tmp_path):
    with Stack(o1, o2, tmp_path) as stack:
        receivers = [("ENV_A_PORT", stack.env["ENV_A_NAME"])]
        if "dual-env" in (o1, o2):
            receivers.append(("ENV_B_PORT", stack.env["ENV_B_NAME"]))
        for port_key, env_name in receivers:
            marker = f"smoke-{env_name}-{int(time.time())}"
            send(stack.ports[port_key], marker)
            out = stack.data_dir / "out"
            for signal in ("traces", "logs", "metrics"):
                recs = wait_for(lambda: jsonl_records(out / f"{signal}.jsonl", marker))
                assert recs, f"{signal} for {env_name} not written"
                assert all(r[0].get("deployment.environment.name") == env_name for r in recs), signal
            span_env = wait_for(lambda: stack.psql(
                "select attributes->'deployment'->'environment'->>'name' from spans "
                f"where name='smoke.span' and attributes->'smoke'->>'id'='{marker}'"))
            assert span_env == env_name, "Phoenix span missing the environment tag as a span attribute"
            if "openobserve" in (o1, o2):
                assert wait_for(lambda: stack.openobserve_search(marker), timeout=90) > 0


def test_phoenix_rejects_logs_and_metrics(tmp_path):
    """findings §8: Phoenix's OTLP endpoint takes traces only, so logs and metrics must not be routed there."""
    import urllib.error
    import urllib.request

    with Stack("none", "none", tmp_path) as stack:
        for path in ("/v1/logs", "/v1/metrics"):
            req = urllib.request.Request(f"http://127.0.0.1:{stack.ports['PHOENIX_PORT']}{path}", data=b"",
                                         method="POST", headers={"Content-Type": "application/x-protobuf"})
            with pytest.raises(urllib.error.HTTPError) as err:
                urllib.request.urlopen(req, timeout=10)
            assert err.value.code == 405, path
