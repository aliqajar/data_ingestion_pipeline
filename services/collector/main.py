from fastapi import FastAPI, HTTPException, Request, Header
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional
from pydantic import BaseModel, ValidationError
from confluent_kafka import Producer
import json
import os
import ssl
import logging
import uuid
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

app = FastAPI(title="Weather Data Collector Service")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Service configuration
PORT = int(os.getenv('COLLECTOR_PORT', '8000'))
SSL_ENABLED = os.getenv('SSL_ENABLED', 'false').lower() == 'true'  # Disabled by default

logger.info(f"Starting Collector service on port {PORT}, SSL: {SSL_ENABLED}")

# SSL Configuration
ssl_context = None
if SSL_ENABLED:
    try:
        logger.info("Setting up SSL context")
        ssl_context = ssl.create_default_context(purpose=ssl.Purpose.CLIENT_AUTH)
        if os.getenv('SSL_CA_CERT_FILE'):
            ssl_context.load_verify_locations(cafile=os.getenv('SSL_CA_CERT_FILE'))
        if os.getenv('SSL_CERT_FILE') and os.getenv('SSL_KEY_FILE'):
            ssl_context.load_cert_chain(certfile=os.getenv('SSL_CERT_FILE'),
                                      keyfile=os.getenv('SSL_KEY_FILE'))
        ssl_context.verify_mode = ssl.CERT_REQUIRED
        ssl_context.check_hostname = True
        logger.info("SSL context successfully created")
    except Exception as e:
        logger.error(f"Failed to create SSL context: {e}")
        SSL_ENABLED = False

logger.info("Setting up Kafka producer")
producer_conf = {
    'bootstrap.servers': os.getenv('KAFKA_BOOTSTRAP_SERVERS', 'kafka:9092')
}
try:
    producer = Producer(producer_conf)
    logger.info("Kafka producer created successfully")
except Exception as e:
    logger.error(f"Failed to create Kafka producer: {e}")
    producer = None

KAFKA_TOPIC = os.getenv('KAFKA_TOPIC', 'weather_data')
KAFKA_DLQ_TOPIC = os.getenv('KAFKA_DLQ_TOPIC', 'weather_data_dlq')

class WeatherData(BaseModel):
    station_id: str
    temperature: float
    humidity: float
    wind_speed: float
    timestamp: str  # ISO8601
    trace_id: Optional[str] = None  # Optional trace ID for tracking

def delivery_report(err, msg, trace_id):
    if err:
        logger.error(f"[TRACE:{trace_id}] Delivery failed: {err}, Message: {msg.value().decode('utf-8')}")
    else:
        logger.info(f"[TRACE:{trace_id}] Message delivered to {msg.topic()}")

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    trace_id = str(uuid.uuid4())
    logger.info(f"[TRACE:{trace_id}] Health check requested")
    status = {
        "status": "healthy",
        "service": "collector",
        "kafka": "disconnected",
        "ssl": "enabled" if SSL_ENABLED else "disabled",
        "trace_id": trace_id
    }
    
    try:
        # Check Kafka connection
        if producer:
            metadata = producer.list_topics(timeout=5.0)
            if metadata:
                status["kafka"] = "connected"
                logger.info("Kafka health check passed")
    except Exception as e:
        status["status"] = "unhealthy"
        status["error"] = str(e)
        logger.error(f"Health check failed: {e}")
    
    return status

@app.post("/weather-data")
async def ingest_weather_data(raw_data: dict, request: Request, x_trace_id: Optional[str] = Header(None)):
    # Get or generate trace ID
    trace_id = x_trace_id or raw_data.get('trace_id') or str(uuid.uuid4())
    logger.info(f"[TRACE:{trace_id}] Received weather data request: {raw_data}")
    
    if not producer:
        logger.error(f"[TRACE:{trace_id}] Kafka producer not available")
        raise HTTPException(status_code=503, detail="Kafka producer not available")
        
    try:
        # Add trace_id if not present
        if 'trace_id' not in raw_data:
            raw_data['trace_id'] = trace_id
            
        logger.info(f"[TRACE:{trace_id}] Validating weather data")
        data = WeatherData(**raw_data)
        payload = data.model_dump_json()
        
        # Pass trace_id to delivery callback
        def dr_callback(err, msg):
            delivery_report(err, msg, trace_id)
            
        logger.info(f"[TRACE:{trace_id}] Sending data to Kafka topic: {KAFKA_TOPIC}")
        producer.produce(KAFKA_TOPIC, payload.encode('utf-8'), callback=dr_callback)
        producer.flush()
        logger.info(f"[TRACE:{trace_id}] Weather data sent to Kafka")
        
    except ValidationError as e:
        # Malformed data to DLQ
        logger.warning(f"[TRACE:{trace_id}] Validation error: {e}")
        dlq_payload = json.dumps({
            "error": str(e),
            "original_message": raw_data,
            "trace_id": trace_id
        })
        
        def dr_callback(err, msg):
            delivery_report(err, msg, trace_id)
            
        producer.produce(KAFKA_DLQ_TOPIC, dlq_payload.encode('utf-8'), callback=dr_callback)
        producer.flush()
        logger.warning(f"[TRACE:{trace_id}] Invalid data sent to DLQ")
        raise HTTPException(status_code=400, detail="Malformed data, sent to DLQ.")
    except Exception as e:
        logger.error(f"[TRACE:{trace_id}] Error ingesting data: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    logger.info(f"[TRACE:{trace_id}] Successfully ingested data")
    return {"status": "success", "detail": "Data ingested successfully"}

if __name__ == "__main__":
    import uvicorn
    logger.info(f"Starting uvicorn server on port {PORT}")
    uvicorn.run(app, host="0.0.0.0", port=PORT)

