import os

from fastapi import FastAPI, Request
from fastapi.responses import Response
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
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Gauge,
    Histogram,
    generate_latest,
    multiprocess,
)

REGISTRY = CollectorRegistry()
multiprocess.MultiProcessCollector(REGISTRY)

Gauge(
    name="build_info",
    documentation="build information",
    multiprocess_mode="livemin",
    registry=REGISTRY,
    labelnames=["version"],
).labels(version=os.getenv("BUILD_VERSION", "UNKNOWN")).set(1)

HTTP_CLIENT_REQUEST_DURATION = Histogram(
    name="http_client_request_duration_seconds",
    documentation="Duration of Redis requests in seconds",
    labelnames=["client", "method", "url", "status_code", "error"],
    registry=REGISTRY,
)


async def metrics_handler(request: Request):
    data = generate_latest(REGISTRY)
    return Response(
        content=data,
        headers={
            "Content-Type": CONTENT_TYPE_LATEST,
            "Content-Length": str(len(data)),
        },
    )


RedisInstrumentor().instrument()  # type: ignore
OTEL_EXPORTER_OTLP_ENDPOINT: str = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "")
DISABLE_OTEL: bool = bool(os.environ.get("DISABLE_OTEL", "0"))
SAMPLE_RATE: float = float(os.environ.get("TRACING_SAMPLE_RATIO", "0.05"))

if not DISABLE_OTEL:
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
    if not DISABLE_OTEL:
        FastAPIInstrumentor.instrument_app(app)  # type: ignore
