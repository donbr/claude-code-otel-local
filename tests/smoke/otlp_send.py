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
