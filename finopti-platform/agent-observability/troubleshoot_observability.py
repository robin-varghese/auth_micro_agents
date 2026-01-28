import sys
import requests
import time
import logging
from opentelemetry import trace
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from phoenix.otel import register
from openinference.instrumentation.google_adk import GoogleADKInstrumentor

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def check_phoenix_reachable(url):
    try:
        response = requests.get(url, timeout=2)
        return response.status_code == 200
    except requests.RequestException:
        return False

def main():
    print("========================================")
    print("🧐 Phoenix Observability Troubleshooter (ADK Edition)")
    print("========================================")

    # 1. Configuration
    # Assuming running from host, so localhost is correct.
    # agent.py uses http://phoenix:6006 because it runs in docker/k8s and accesses the service 'phoenix'
    PHOENIX_HOST = "localhost" 
    PHOENIX_PORT = "6006"
    PHOENIX_URL = f"http://{PHOENIX_HOST}:{PHOENIX_PORT}"
    TRACE_ENDPOINT = f"{PHOENIX_URL}/v1/traces"
    
    print(f"\n[1] Checking Phoenix Connection at {PHOENIX_URL}...")
    if check_phoenix_reachable(PHOENIX_URL):
        print(f"✅ Phoenix UI is reachable.")
    else:
        print(f"❌ Phoenix UI is NOT reachable at {PHOENIX_URL}. Ensure it is running.")
        sys.exit(1)

    # 2. Setup ADK Tracing (matching agent.py)
    print(f"\n[2] Initializing ADK Instrumentation...")
    
    try:
        # Use register() just like agent.py
        # This registers the BatchSpanProcessor by default
        tracer_provider = register(
            project_name="troubleshoot-script-adk",
            endpoint=TRACE_ENDPOINT,
            set_global_tracer_provider=True
        )
        
        # Add Google ADK Instrumentor
        GoogleADKInstrumentor().instrument(tracer_provider=tracer_provider)
        
        # Add SimpleSpanProcessor for immediate export (debugging)
        # Note: agent.py adds this ON TOP of what register() adds.
        http_exporter = OTLPSpanExporter(endpoint=TRACE_ENDPOINT)
        tracer_provider.add_span_processor(SimpleSpanProcessor(http_exporter))
        
        print(f"✅ Tracer provider registered with endpoint: {TRACE_ENDPOINT}")
        
    except Exception as e:
        print(f"❌ Failed to initialize tracing: {e}")
        print("   Make sure you have 'arize-phoenix-otel' and 'openinference-instrumentation-google-adk' installed.")
        sys.exit(1)

    # 3. Send Test Trace
    print(f"\n[3] Sending Test Trace...")
    tracer = trace.get_tracer(__name__)
    
    try:
        with tracer.start_as_current_span("adk-troubleshoot-test") as span:
            span.set_attribute("test.run_id", str(int(time.time())))
            span.set_attribute("status", "ok")
            span.add_event("performing_troubleshooting_event")
            
            # Simulate some work
            print("   Simulating work...")
            time.sleep(0.5)
            
        print(f"✅ Test trace sent successfully to {TRACE_ENDPOINT}")
        print(f"   Check your Phoenix UI project 'troubleshoot-script-adk' to verify.")
        
    except Exception as e:
        print(f"❌ Failed to send trace: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
