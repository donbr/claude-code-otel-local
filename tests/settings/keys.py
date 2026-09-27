BASELINE = {
    "CLAUDE_CODE_ENABLE_TELEMETRY": "1",
    "CLAUDE_CODE_ENHANCED_TELEMETRY_BETA": "1",
    "OTEL_TRACES_EXPORTER": "otlp",
    "OTEL_METRICS_EXPORTER": "otlp",
    "OTEL_LOGS_EXPORTER": "otlp",
    "OTEL_EXPORTER_OTLP_PROTOCOL": "http/protobuf",
}
CONTENT_KEYS = ("OTEL_LOG_USER_PROMPTS", "OTEL_LOG_ASSISTANT_RESPONSES", "OTEL_LOG_TOOL_DETAILS",
                "OTEL_LOG_TOOL_CONTENT", "OTEL_LOG_RAW_API_BODIES")
PER_LAUNCH_KEYS = ("OTEL_RESOURCE_ATTRIBUTES", "ENABLE_BETA_TRACING_DETAILED", "BETA_TRACING_ENDPOINT")
VENDOR_ENV_PREFIXES = ("ARIZE_", "PHOENIX_", "LANGFUSE_", "CC_LANGFUSE_")
VENDOR_MARKERS = ("arize", "langfuse")


def violations(settings: dict, endpoint: str) -> list[str]:
    """Key names that break the baseline; never values."""
    env = settings.get("env", {})
    out = [k for k, v in BASELINE.items() if env.get(k) != v]
    if env.get("OTEL_EXPORTER_OTLP_ENDPOINT") != endpoint:
        out.append("OTEL_EXPORTER_OTLP_ENDPOINT")
    out += [k for k in env if k.startswith("OTEL_EXPORTER_OTLP_") and k not in ("OTEL_EXPORTER_OTLP_ENDPOINT", "OTEL_EXPORTER_OTLP_PROTOCOL")]
    out += [k for k in CONTENT_KEYS if env.get(k) not in (None, "", "0", "false")]
    out += [k for k in PER_LAUNCH_KEYS if k in env]
    out += [k for k in env if k.startswith(VENDOR_ENV_PREFIXES)]
    out += [k for k in ("OTEL_LOGS_EXPORT_INTERVAL",) if k in env]
    interval = str(env.get("OTEL_METRIC_EXPORT_INTERVAL") or "60000").strip()
    if not interval.isdigit() or int(interval) < 60000:
        out.append("OTEL_METRIC_EXPORT_INTERVAL")
    for section in ("extraKnownMarketplaces", "pluginConfigs"):
        out += [f"{section}:{k}" for k in settings.get(section, {}) if any(m in k.lower() for m in VENDOR_MARKERS)]
    out += [f"enabledPlugins:{k}" for k, on in settings.get("enabledPlugins", {}).items()
            if on and any(m in k.lower() for m in VENDOR_MARKERS)]
    return sorted(set(out))
