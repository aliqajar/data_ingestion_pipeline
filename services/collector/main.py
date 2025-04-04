from fastapi import FastAPI, HTTPException, Request, Header
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional, List, Dict
from pydantic import BaseModel, ValidationError
from confluent_kafka import Producer
import json
import os
import ssl
import logging
import uuid
import asyncio
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

class WeatherDataBatch(BaseModel):
    records: List[WeatherData]
    batch_id: Optional[str] = None

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

async def process_weather_data(raw_data: dict, trace_id: str):
    """Process a single weather data record"""
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
        return True, None
        
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
        return False, str(e)
    except Exception as e:
        logger.error(f"[TRACE:{trace_id}] Error processing data: {e}")
        return False, str(e)

@app.post("/weather-data")
async def ingest_weather_data(raw_data: dict, request: Request, x_trace_id: Optional[str] = Header(None)):
    """Ingest a single weather data record"""
    # Get or generate trace ID
    trace_id = x_trace_id or raw_data.get('trace_id') or str(uuid.uuid4())
    logger.info(f"[TRACE:{trace_id}] Received weather data request: {raw_data}")
    
    if not producer:
        logger.error(f"[TRACE:{trace_id}] Kafka producer not available")
        raise HTTPException(status_code=503, detail="Kafka producer not available")
    
    success, error = await process_weather_data(raw_data, trace_id)
    
    # Flush all messages
    producer.flush()
    
    if not success:
        raise HTTPException(status_code=400, detail=f"Error processing data: {error}")
    
    logger.info(f"[TRACE:{trace_id}] Successfully ingested data")
    return {"status": "success", "detail": "Data ingested successfully"}

@app.post("/weather-data/batch")
async def ingest_weather_data_batch(batch_data: dict, request: Request, x_trace_id: Optional[str] = Header(None)):
    """Ingest multiple weather data records in a batch"""
    # Generate batch ID and use as trace ID if not provided
    batch_id = x_trace_id or batch_data.get('batch_id') or str(uuid.uuid4())
    logger.info(f"[BATCH:{batch_id}] Received batch with {len(batch_data.get('records', []))} records")
    
    if not producer:
        logger.error(f"[BATCH:{batch_id}] Kafka producer not available")
        raise HTTPException(status_code=503, detail="Kafka producer not available")
    
    # Validate the batch structure
    try:
        if 'records' not in batch_data or not isinstance(batch_data['records'], list):
            logger.error(f"[BATCH:{batch_id}] Invalid batch format: 'records' field missing or not a list")
            raise HTTPException(status_code=400, detail="Invalid batch format: 'records' field missing or not a list")
        
        # Process each record in the batch
        results = []
        for index, record in enumerate(batch_data['records']):
            # Generate a unique trace ID for each record based on the batch ID
            record_trace_id = f"{batch_id}-{index}"
            
            # Process the record
            success, error = await process_weather_data(record, record_trace_id)
            results.append({
                "index": index,
                "success": success,
                "error": error
            })
        
        # Flush all messages at once for efficiency
        producer.flush()
        
        # Count successes and failures
        successes = sum(1 for r in results if r["success"])
        failures = len(results) - successes
        
        logger.info(f"[BATCH:{batch_id}] Batch processing complete: {successes} successes, {failures} failures")
        
        # Return a summary with details on failures
        return {
            "status": "completed",
            "batch_id": batch_id,
            "total": len(results),
            "successful": successes,
            "failed": failures,
            "failures": [r for r in results if not r["success"]]
        }
            
    except Exception as e:
        logger.error(f"[BATCH:{batch_id}] Error processing batch: {e}")
        raise HTTPException(status_code=500, detail=f"Error processing batch: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    logger.info(f"Starting uvicorn server on port {PORT}")
    uvicorn.run(app, host="0.0.0.0", port=PORT)

