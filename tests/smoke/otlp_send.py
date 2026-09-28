"""Send one span, one log record and one metric over OTLP/HTTP, each tagged smoke.id=<marker>."""

import logging

from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import SimpleLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor


def send(port: int, marker: str) -> None:
    base = f"http://127.0.0.1:{port}"
    resource = Resource.create({"service.name": "claude-code-otel-local-smoke"})

    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(SimpleSpanProcessor(OTLPSpanExporter(endpoint=f"{base}/v1/traces")))
    with tracer_provider.get_tracer("smoke").start_as_current_span("smoke.span") as span:
        span.set_attribute("smoke.id", marker)
    tracer_provider.shutdown()

    logger_provider = LoggerProvider(resource=resource)
    logger_provider.add_log_record_processor(SimpleLogRecordProcessor(OTLPLogExporter(endpoint=f"{base}/v1/logs")))
    logger = logging.getLogger(f"smoke.{marker}")
    logger.propagate = False
    logger.addHandler(LoggingHandler(logger_provider=logger_provider))
    logger.warning("smoke log %s", marker, extra={"smoke.id": marker})
    logger_provider.shutdown()

    reader = PeriodicExportingMetricReader(OTLPMetricExporter(endpoint=f"{base}/v1/metrics"), export_interval_millis=500)
    meter_provider = MeterProvider(resource=resource, metric_readers=[reader])
    meter_provider.get_meter("smoke").create_counter("smoke.count").add(1, {"smoke.id": marker})
    meter_provider.shutdown()


def send_claude_like(port: int, marker: str, prompt: str, reply: str, tool_mode: str = "none",
                     preset: dict | None = None) -> None:
    """One trace shaped like Claude Code's native spans (names and attribute keys as of 2.1.283).

    interaction(user_prompt) -> llm_request(response.model_output, token counts) and tool(tool_name).
    Pass "<REDACTED>" as prompt or reply to mimic a session without content capture.
    tool_mode: "none" (no tool flags), "detailed" (tool_input/new_context JSON on the span, as with
    ENABLE_BETA_TRACING_DETAILED), or "flags" (full_command + a tool.output event, as with
    OTEL_LOG_TOOL_DETAILS and OTEL_LOG_TOOL_CONTENT without detailed tracing).
    preset: OpenInference attributes the sender already set on the llm_request and tool spans; the
    collector must leave them untouched.
    """
    resource = Resource.create({"service.name": "claude-code", "smoke.id": marker})
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(SimpleSpanProcessor(OTLPSpanExporter(endpoint=f"http://127.0.0.1:{port}/v1/traces")))
    tracer = provider.get_tracer("com.anthropic.claude_code.tracing")
    with tracer.start_as_current_span("claude_code.interaction") as span:
        span.set_attributes({"smoke.id": marker, "user_prompt": prompt, "interaction.sequence": 1})
        with tracer.start_as_current_span("claude_code.llm_request") as llm:
            llm.set_attributes({"smoke.id": marker, "response.model_output": reply, "gen_ai.request.model": "claude-test",
                                "gen_ai.system": "anthropic", "input_tokens": 2, "cache_read_tokens": 10,
                                "cache_creation_tokens": 100, "output_tokens": 5})
            llm.set_attributes(preset or {})
        with tracer.start_as_current_span("claude_code.tool") as tool:
            tool.set_attributes({"smoke.id": marker, "tool_name": "Bash"})
            if tool_mode == "detailed":
                tool.set_attributes({
                    "tool_input": f'[TOOL INPUT: Bash]\n{{"command":"echo {marker}"}}',
                    "new_context": f'[TOOL RESULT: Bash]\n{{"stdout":"{marker}","stderr":""}}'})
            elif tool_mode == "flags":
                tool.set_attribute("full_command", f"echo {marker}")
                tool.add_event("tool.output", {"bash_command": f"echo {marker}", "output": f"{marker}\n"})
            tool.set_attributes(preset or {})
    provider.shutdown()
