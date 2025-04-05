import os
import json
import time
import asyncio
import ssl
import logging
import uuid
import signal
from multiprocessing import Manager
from typing import Optional
from collections import defaultdict
from confluent_kafka import Consumer, KafkaError, Producer
from dotenv import load_dotenv
from pydantic import BaseModel, field_validator
import psycopg2
from psycopg2.extras import execute_values
from fastapi import FastAPI
import uvicorn
import threading
from aiokafka import AIOKafkaConsumer
from contextlib import asynccontextmanager

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

# Service configuration
PORT = int(os.getenv('CONSUMER_PORT', '8002'))
SSL_ENABLED = False  # Force disable SSL for now

logger.info(f"Starting Consumer service on port {PORT}, SSL: {SSL_ENABLED}")

# Create a Manager for thread-safe shared objects
manager = Manager()

# SSL Configuration - completely skip for now
ssl_context = None

# Set up signal handlers for graceful shutdown
shutdown_event = threading.Event()

def signal_handler():
    logger.info("Received shutdown signal")
    shutdown_event.set()

# Register signal handlers
for sig in (signal.SIGINT, signal.SIGTERM):
    signal.signal(sig, lambda sig, frame: signal_handler())

# Create a lifespan context manager instead of using on_event
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup code
    logger.info("Starting consumer loop")
    consume_task = asyncio.create_task(consume_loop())
    
    # Start the timer task for regular flushing
    flush_timer_task = asyncio.create_task(periodic_flush_task())
    
    yield  # This is where the application runs
    
    # Shutdown code
    logger.info("Shutting down - flushing any remaining records to database")
    
    # Cancel the flush timer task
    flush_timer_task.cancel()
    
    # Check if there are any records in the buffer and flush them
    if len(buffer) > 0:
        logger.info(f"Flushing {len(buffer)} remaining records before shutdown")
        await persist_batch("shutdown")
    
    if consumer:
        consumer.close()
    if cursor:
        cursor.close()
    if conn:
        conn.close()
    
    # Log final duplicate stats
    logger.info("====== FINAL DEDUPLICATION STATS ======")
    logger.info(f"Total messages processed: {stats['messages_processed']}")
    logger.info(f"In-memory duplicates removed: {stats['in_memory_duplicates']}")
    duplicate_percent = 0
    if stats["messages_processed"] > 0:
        duplicate_percent = (stats["in_memory_duplicates"] / stats["messages_processed"]) * 100
    logger.info(f"Duplicate percentage: {duplicate_percent:.2f}%")
    logger.info("=======================================")

# Create the FastAPI app with lifespan
app = FastAPI(title="Weather Data Consumer Service", lifespan=lifespan)

KAFKA_TOPIC = os.getenv('KAFKA_TOPIC', 'weather_data')
KAFKA_DLQ_TOPIC = os.getenv('KAFKA_DLQ_TOPIC', 'weather_data_dlq')
BATCH_SIZE = int(os.getenv('BATCH_SIZE', '100'))
BATCH_INTERVAL = int(os.getenv('BATCH_INTERVAL', '5'))  # seconds

kafka_bootstrap_servers = os.getenv('KAFKA_BOOTSTRAP_SERVERS', 'kafka:9092')
logger.info(f"Setting up Kafka consumer with bootstrap servers: {kafka_bootstrap_servers}")

consumer_conf = {
    'bootstrap.servers': kafka_bootstrap_servers,
    'group.id': 'weather_consumers',
    'auto.offset.reset': 'earliest',
}

try:
    consumer = Consumer(consumer_conf)
    consumer.subscribe([KAFKA_TOPIC])
    logger.info(f"Subscribed to topic: {KAFKA_TOPIC}")
except Exception as e:
    logger.error(f"Failed to create Kafka consumer: {e}")
    consumer = None

# DB setup
logger.info("Setting up PostgreSQL connection")
try:
    conn = psycopg2.connect(
        host=os.getenv('POSTGRES_HOST', 'postgres'),
        port=os.getenv('POSTGRES_PORT', '5432'),
        dbname=os.getenv('POSTGRES_DB', 'weather_db'),
        user=os.getenv('POSTGRES_USER', 'weather_user'),
        password=os.getenv('POSTGRES_PASSWORD', 'weather_password')
    )
    cursor = conn.cursor()
    logger.info("PostgreSQL connection established")
except Exception as e:
    logger.error(f"Failed to connect to PostgreSQL: {e}")
    conn = None
    cursor = None

class WeatherData(BaseModel):
    station_id: str
    temperature: float
    humidity: float
    wind_speed: float
    timestamp: str  # ISO8601 format
    trace_id: Optional[str] = None  # Added trace_id field for tracking

    @field_validator('temperature')
    @classmethod
    def validate_temperature(cls, v):
        if not (-100 <= v <= 60):
            raise ValueError('Temperature out of realistic range')
        return v
    
    @field_validator('humidity')
    @classmethod
    def validate_humidity(cls, v):
        if not (0 <= v <= 100):
            raise ValueError('Humidity out of realistic range')
        return v
    
    @field_validator('wind_speed')
    @classmethod
    def validate_wind_speed(cls, v):
        if v < 0:
            raise ValueError('Wind speed cannot be negative')
        return v

def send_to_dlq(msg, trace_id=None):
    try:
        if not trace_id and isinstance(msg, bytes):
            # Try to extract trace ID from the message
            try:
                data = json.loads(msg.decode('utf-8'))
                trace_id = data.get('trace_id', 'unknown')
            except:
                trace_id = 'unknown'
        
        logger.info(f"[TRACE:{trace_id}] Sending message to DLQ")
        producer_conf = {'bootstrap.servers': kafka_bootstrap_servers}
        producer = Producer(producer_conf)
        
        # If msg is a dict, add trace_id and convert to bytes
        if isinstance(msg, dict):
            if trace_id:
                msg['trace_id'] = trace_id
            msg = json.dumps(msg).encode('utf-8')
            
        producer.produce(KAFKA_DLQ_TOPIC, msg)
        producer.flush()
        logger.info(f"[TRACE:{trace_id}] Message sent to DLQ")
    except Exception as e:
        logger.error(f"[TRACE:{trace_id}] Failed to send to DLQ: {e}")

# Initialize global variables at the module level
buffer = manager.dict()  # Thread-safe dictionary
buffer_lock = threading.Lock()
stats = {
    "messages_processed": 0,
    "batches_persisted": 0,
    "in_memory_duplicates": 0
}
last_flush_time = time.time()  # Track last flush time globally

async def persist_batch(trace_id="system"):
    """Persist a batch of data to the database"""
    global buffer, stats, last_flush_time
    
    if not buffer:
        logger.info(f"[TRACE:{trace_id}] No data to persist")
        return 0
    
    logger.info(f"[TRACE:{trace_id}] Persisting batch of {len(buffer)} records")
    
    # Make a copy of the buffer and clear it
    with buffer_lock:
        data_to_persist = list(buffer.values())
        buffer.clear()
    
    # Connect to the database
    try:
        conn = psycopg2.connect(
            host=os.getenv('POSTGRES_HOST', 'postgres'),
            port=os.getenv('POSTGRES_PORT', '5432'),
            dbname=os.getenv('POSTGRES_DB', 'weather_db'),
            user=os.getenv('POSTGRES_USER', 'weather_user'),
            password=os.getenv('POSTGRES_PASSWORD', 'weather_password')
        )
        cursor = conn.cursor()
        
        # Directly insert all records with ON CONFLICT DO UPDATE
        # No pre-checks - just let the database handle conflicts
        records_processed = 0
        for data in data_to_persist:
            cursor.execute(
                """
                INSERT INTO weather (station_id, temperature, humidity, wind_speed, timestamp) 
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (station_id, timestamp) 
                DO UPDATE SET temperature = EXCLUDED.temperature, 
                              humidity = EXCLUDED.humidity,
                              wind_speed = EXCLUDED.wind_speed
                """,
                (
                    data['station_id'],
                    data['temperature'],
                    data['humidity'],
                    data['wind_speed'],
                    data['timestamp']
                )
            )
            records_processed += 1
        
        # Commit the transaction
        conn.commit()
        
        # Update batches persisted counter
        with buffer_lock:
            stats["batches_persisted"] += 1
        
        # Log the in-memory duplication stats (focus on what matters)
        if stats["in_memory_duplicates"] > 0:
            logger.info(f"DUPLICATE LEDGER: In-memory deduplication has found {stats['in_memory_duplicates']} duplicates")
            duplicate_percent = 0
            if stats["messages_processed"] > 0:
                duplicate_percent = (stats["in_memory_duplicates"] / stats["messages_processed"]) * 100
            logger.info(f"Current duplicate percentage: {duplicate_percent:.2f}%")
        
        logger.info(f"[TRACE:{trace_id}] Successfully persisted batch of {records_processed} records.")
        
        # Close cursor and connection
        cursor.close()
        conn.close()
        
        # Update the last flush time
        last_flush_time = time.time()
        
        return records_processed
    except Exception as e:
        logger.error(f"[TRACE:{trace_id}] Error persisting batch: {e}")
        return 0

async def consume():
    """Consume weather data from Kafka"""
    global buffer, stats, last_flush_time, shutdown_event
    
    try:
        # Subscribe to topic
        logger.info(f"Connecting to Kafka at {kafka_bootstrap_servers}")
        consumer = AIOKafkaConsumer(
            KAFKA_TOPIC,
            bootstrap_servers=kafka_bootstrap_servers,
            group_id='weather_consumers',
            enable_auto_commit=True,
            auto_commit_interval_ms=1000,
            auto_offset_reset='earliest'
        )
        
        # Start the consumer
        await consumer.start()
        
        # Log partition assignments
        partitions = consumer.assignment()
        logger.info(f"Consumer assigned to partitions: {partitions}")
        
        # Process messages
        async for msg in consumer:
            # Check if shutdown was requested
            if shutdown_event.is_set():
                logger.info("Shutdown requested, stopping consumer loop")
                break
                
            try:
                # Log partition information for tracing
                logger.debug(f"Processing message from partition {msg.partition}, offset {msg.offset}")
                
                # Parse message
                value = json.loads(msg.value.decode('utf-8'))
                trace_id = value.get('trace_id', 'unknown')
                logger.info(f"[TRACE:{trace_id}] Received message: station={value.get('station_id')}, time={value.get('timestamp')}")
                
                # Validate data using model (but don't store the model itself)
                data = WeatherData(
                    station_id=value.get('station_id'),
                    temperature=value.get('temperature'),
                    humidity=value.get('humidity'),
                    wind_speed=value.get('wind_speed'),
                    timestamp=value.get('timestamp'),
                    trace_id=trace_id
                )
                
                # Use station_id and timestamp as unique key
                unique_key = f"{data.station_id}:{data.timestamp}"
                
                # Check if this is a duplicate (for logging purposes)
                is_duplicate = unique_key in buffer
                if is_duplicate:
                    logger.info(f"[TRACE:{trace_id}] DEDUPLICATION: Replacing existing record for {data.station_id} at {data.timestamp}")
                    with buffer_lock:
                        stats["in_memory_duplicates"] += 1
                
                # Store as dict in buffer (this would overwrite any existing record with the same key)
                # Important: Store as dict, not Pydantic model
                buffer[unique_key] = {
                    'station_id': data.station_id,
                    'temperature': data.temperature,
                    'humidity': data.humidity,
                    'wind_speed': data.wind_speed,
                    'timestamp': data.timestamp
                }
                with buffer_lock:
                    stats["messages_processed"] += 1
                
                # Batch flush condition - just check size here, TTL is handled by the timer task
                if len(buffer) >= BATCH_SIZE:
                    if buffer:
                        logger.info(f"SIZE FLUSH: Buffer reached {len(buffer)} records (max={BATCH_SIZE})")
                        await persist_batch(trace_id)
                        last_flush_time = time.time()  # Update global last flush time
                
            except Exception as e:
                logger.error(f"Error processing message: {e}")
                try:
                    send_to_dlq(msg.value, trace_id)
                except:
                    logger.error(f"Failed to send message to DLQ")
            
            # Small sleep to prevent CPU spinning
            await asyncio.sleep(0.01)
            
    except Exception as e:
        logger.error(f"Error in consume function: {e}")
        if consumer:
            await consumer.stop()
    finally:
        # Final flush of any remaining records
        if buffer:
            logger.info(f"Final flush of {len(buffer)} records at consumer shutdown")
            await persist_batch("consumer_shutdown")
        
        if consumer:
            await consumer.stop()

async def consume_loop():
    """Start the async consumer loop"""
    if not consumer:
        logger.error("Cannot start consume loop: Kafka consumer not available")
        return
    
    logger.info("Starting consume loop")
    
    try:
        # Call the async consume function
        await consume()
    except Exception as e:
        logger.error(f"Error in consume loop: {e}")
    finally:
        logger.info("Consume loop ended")

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    trace_id = str(uuid.uuid4())
    logger.info(f"[TRACE:{trace_id}] Health check requested")
    status = {
        "status": "healthy",
        "service": "consumer",
        "kafka": "disconnected",
        "postgresql": "disconnected",
        "ssl": "enabled" if SSL_ENABLED else "disabled",
        "trace_id": trace_id
    }
    
    # Check Kafka connection
    if consumer:
        try:
            consumer.list_topics(timeout=5.0)
            status["kafka"] = "connected"
            logger.info("Kafka health check passed")
        except Exception as e:
            logger.error(f"Kafka health check failed: {e}")
    
    # Check PostgreSQL connection
    if conn:
        try:
            with conn.cursor() as cursor:
                cursor.execute("SELECT 1")
            status["postgresql"] = "connected"
            logger.info("PostgreSQL health check passed")
        except Exception as e:
            logger.error(f"PostgreSQL health check failed: {e}")
    
    # Update overall status
    if status["kafka"] != "connected" or status["postgresql"] != "connected":
        status["status"] = "degraded"
        logger.warning("Service is in degraded state")
    
    return status

@app.get("/stats")
async def get_stats():
    """Get consumer stats"""
    global stats, buffer
    return {
        "messages_processed": stats["messages_processed"],
        "batches_persisted": stats["batches_persisted"],
        "buffer_size": len(buffer),
        "in_memory_duplicates": stats["in_memory_duplicates"]
    }

@app.post("/flush")
async def flush_buffer():
    """Manually flush the buffer to the database"""
    global buffer
    
    buffer_size = len(buffer)
    if buffer_size == 0:
        return {"message": "No data to flush", "flushed": 0}
    
    logger.info(f"Manual flush requested for {buffer_size} records")
    records_processed = await persist_batch("manual_flush")
    
    return {
        "message": f"Successfully flushed buffer",
        "flushed": buffer_size
    }

async def periodic_flush_task():
    """Periodically flush the buffer based on time"""
    global buffer, last_flush_time
    
    logger.info(f"Starting periodic flush task (interval={BATCH_INTERVAL}s)")
    
    while not shutdown_event.is_set():
        try:
            # Sleep for a quarter of the interval to be more responsive to shutdown
            await asyncio.sleep(BATCH_INTERVAL / 4)
            
            # Check if it's time to flush
            current_time = time.time()
            time_since_last_flush = current_time - last_flush_time
            
            if time_since_last_flush >= BATCH_INTERVAL:
                # Check if there's anything to flush
                if len(buffer) > 0:
                    logger.info(f"TTL FLUSH: Buffer not flushed for {time_since_last_flush:.1f}s, flushing {len(buffer)} records")
                    await persist_batch("ttl_flush")
                
                # Update the last flush time even if no data was flushed
                last_flush_time = current_time
            
        except Exception as e:
            logger.error(f"Error in periodic flush task: {e}")
            # Wait a bit before retrying
            await asyncio.sleep(1)

if __name__ == "__main__":
    logger.info(f"Starting uvicorn server on port {PORT}")
    uvicorn.run(app, host="0.0.0.0", port=PORT)
