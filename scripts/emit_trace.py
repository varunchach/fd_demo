"""Emit a real OpenTelemetry trace for a fraud-detection inference request,
exported via OTLP to the in-cluster OpenTelemetry Collector, which forwards to Tempo."""
import pickle

import numpy as np
import onnxruntime as rt
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

resource = Resource.create({"service.name": "fraud-detection-inference"})
provider = TracerProvider(resource=resource)
provider.add_span_processor(
    BatchSpanProcessor(
        OTLPSpanExporter(endpoint="fraud-otel-collector.fraud-detection.svc.cluster.local:4317", insecure=True)
    )
)
trace.set_tracer_provider(provider)
tracer = trace.get_tracer("fraud-detection-demo")

with tracer.start_as_current_span("fraud-detection-request") as parent:
    with tracer.start_as_current_span("load-model"):
        sess = rt.InferenceSession("models/fraud/1/model.onnx", providers=rt.get_available_providers())
        input_name = sess.get_inputs()[0].name
        output_name = sess.get_outputs()[0].name

    with tracer.start_as_current_span("load-scaler"):
        with open("artifact/scaler.pkl", "rb") as handle:
            scaler = pickle.load(handle)

    with tracer.start_as_current_span("score-transaction") as span:
        sally_transaction = [[0.3111400080477545, 1.9459399775518593, 1.0, 0.0, 0.0]]
        scaled = scaler.transform(sally_transaction).astype(np.float32)
        prediction = sess.run([output_name], {input_name: scaled})
        score = float(np.squeeze(prediction))
        span.set_attribute("fraud.score", score)
        span.set_attribute("fraud.is_fraud", score > 0.95)
        print(f"Fraud score: {score:.5f}, is_fraud: {score > 0.95}")

provider.shutdown()
print("Trace exported.")
