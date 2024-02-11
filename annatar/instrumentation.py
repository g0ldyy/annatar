import os

from fastapi import FastAPI
from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor  # type: ignore
from opentelemetry.instrumentation.redis import RedisInstrumentor  # type: ignore
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import (
    ConsoleMetricExporter,
    PeriodicExportingMetricReader,
)
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.sdk.trace.sampling import TraceIdRatioBased

RedisInstrumentor().instrument()  # type: ignore
OTEL_EXPORTER_OTLP_ENDPOINT: str = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "")
SAMPLE_RATE: float = float(os.environ.get("TRACING_SAMPLE_RATIO", "0.05"))

if OTEL_EXPORTER_OTLP_ENDPOINT:
    # tracing
    provider = TracerProvider(sampler=TraceIdRatioBased(SAMPLE_RATE))
    processor = BatchSpanProcessor(OTLPSpanExporter())
    provider.add_span_processor(processor)
    trace.set_tracer_provider(provider)
    # metrics
    meter_reader = PeriodicExportingMetricReader(OTLPMetricExporter())
    metrics_provider = MeterProvider(metric_readers=[meter_reader])
    metrics.set_meter_provider(metrics_provider)
else:
    # traces
    provider = TracerProvider()
    processor = BatchSpanProcessor(ConsoleSpanExporter())
    provider.add_span_processor(processor)
    trace.set_tracer_provider(provider)
    # metrics
    meter_reader = PeriodicExportingMetricReader(ConsoleMetricExporter())
    metrics_provider = MeterProvider(metric_readers=[meter_reader])
    metrics.set_meter_provider(metrics_provider)


def init():
    pass


def instrument_fastapi(app: FastAPI):
    FastAPIInstrumentor.instrument_app(app)  # type: ignore
