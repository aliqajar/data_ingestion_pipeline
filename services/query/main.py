from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional, List, Dict, Any
import psycopg2
import redis
import os
import json
import hashlib
import logging
import uuid
from dotenv import load_dotenv
from datetime import datetime, timedelta
import time
from fastapi import Query
from contextlib import asynccontextmanager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

load_dotenv()

# Service configuration
PORT = int(os.getenv('QUERY_PORT', '8001'))
HOST = os.getenv('HOST', '0.0.0.0')
SSL_ENABLED = os.getenv('SSL_ENABLED', 'false').lower() == 'true'  # Add SSL setting for consistency

logger.info(f"Starting Query service on {HOST}:{PORT}, SSL: {SSL_ENABLED}")

# Database setup
def get_db_connection():
    try:
        logger.info("Attempting to connect to PostgreSQL...")
        conn = psycopg2.connect(
            host=os.getenv('POSTGRES_HOST', 'postgres'),
            port=os.getenv('POSTGRES_PORT', '5432'),
            dbname=os.getenv('POSTGRES_DB', 'weather_db'),
            user=os.getenv('POSTGRES_USER', 'weather_user'),
            password=os.getenv('POSTGRES_PASSWORD', 'weather_password')
        )
        logger.info("Successfully connected to PostgreSQL")
        return conn
    except Exception as e:
        logger.error(f"Database connection error: {e}")
        return None

# Redis setup
def get_redis_client():
    try:
        logger.info("Attempting to connect to Redis...")
        client = redis.Redis(
            host=os.getenv('REDIS_HOST', 'redis'),
            port=int(os.getenv('REDIS_PORT', '6379')),
            db=0,
            decode_responses=True
        )
        logger.info("Successfully connected to Redis")
        return client
    except Exception as e:
        logger.error(f"Redis connection error: {e}")
        return None

CACHE_TTL = int(os.getenv('CACHE_TTL', '300'))  # 5 minutes cache TTL

def cache_key(query: str, params: tuple):
    """Create a cache key that handles datetime objects properly"""
    # Convert datetime objects to ISO format strings
    serializable_params = []
    for param in params:
        if isinstance(param, datetime):
            serializable_params.append(param.isoformat())
        else:
            serializable_params.append(param)
    
    key_str = query + json.dumps(serializable_params, sort_keys=True)
    return hashlib.sha256(key_str.encode()).hexdigest()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Wait for database to be ready
    max_retries = 30
    retry_delay = 2
    for i in range(max_retries):
        conn = get_db_connection()
        if conn:
            try:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1 FROM weather LIMIT 1")
                    logger.info("Database is ready")
                    conn.close()
                    break
            except Exception as e:
                logger.warning(f"Database not ready (attempt {i+1}/{max_retries}): {e}")
                conn.close()
        time.sleep(retry_delay)
    else:
        logger.error("Failed to connect to database after maximum retries")
    
    yield
    
    # Cleanup
    logger.info("Shutting down Query service")

app = FastAPI(title="Weather Data Query Service", lifespan=lifespan)

# --- Add CORS middleware --- 
origins = [
    "http://localhost",
    "http://localhost:3000", # Default React dev port
    "http://localhost:3001", # Possible React dev port (if using start:query)
    # Add any other origins if your UI might be served from elsewhere
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"], # Allow all methods (GET, POST, etc.)
    allow_headers=["*"], # Allow all headers
)
# --- End CORS middleware ---

@app.get("/health")
async def health_check():
    """Health check endpoint that verifies database and Redis connections"""
    trace_id = str(uuid.uuid4())
    logger.info(f"[TRACE:{trace_id}] Health check requested")
    
    status = "healthy"
    db_status = "healthy"
    redis_status = "healthy"
    
    # Check PostgreSQL connection
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
        logger.info(f"[TRACE:{trace_id}] PostgreSQL health check passed")
    except Exception as e:
        logger.error(f"[TRACE:{trace_id}] PostgreSQL health check failed: {str(e)}")
        db_status = "degraded"
        status = "degraded"
    
    # Check Redis connection - but don't fail health check if Redis is down
    try:
        redis_client = get_redis_client()
        if redis_client:
            redis_client.ping()
            logger.info(f"[TRACE:{trace_id}] Redis health check passed")
        else:
            raise Exception("Redis client not available")
    except Exception as e:
        logger.error(f"[TRACE:{trace_id}] Redis health check failed: {str(e)}")
        redis_status = "degraded"
        # Don't set overall status to degraded for Redis issues
    
    logger.info(f"[TRACE:{trace_id}] Health check completed with status: {status}")
    return {
        "status": status,
        "service": "query",
        "components": {
            "database": db_status,
            "redis": redis_status
        }
    }

@app.get("/weather/{station_id}")
def get_weather_data(
    station_id: str,
    start_time: datetime = Query(default=None),
    end_time: datetime = Query(default=None)
):
    """Get all weather data for a specific station with optional time range filter"""
    trace_id = str(uuid.uuid4())
    logger.info(f"[TRACE:{trace_id}] Weather data requested for station {station_id}")
    
    if start_time and end_time:
        logger.info(f"[TRACE:{trace_id}] Date range: {start_time} to {end_time}")
    
    # Try to get from cache first
    cache_key = f"weather:{station_id}:{start_time}:{end_time}"
    try:
        redis_client = get_redis_client()
        if redis_client:
            cached_data = redis_client.get(cache_key)
            if cached_data:
                logger.info(f"[TRACE:{trace_id}] Cache hit for query")
                return json.loads(cached_data)
    except Exception as e:
        logger.error(f"[TRACE:{trace_id}] Redis error: {str(e)}")
        # Continue with DB query if Redis fails
    
    try:
        logger.info(f"[TRACE:{trace_id}] Querying database")
        conn = get_db_connection()
        with conn.cursor() as cur:
            query = """
                SELECT station_id, temperature, humidity, wind_speed, timestamp
                FROM weather
                WHERE station_id = %s
            """
            params = [station_id]
            
            if start_time and end_time:
                query += " AND timestamp BETWEEN %s AND %s"
                params.extend([start_time, end_time])
            
            # Order by timestamp in descending order
            query += " ORDER BY timestamp DESC"
            
            cur.execute(query, params)
            rows = cur.fetchall()
            
            results = [{
                "station_id": row[0],
                "temperature": row[1],
                "humidity": row[2],
                "wind_speed": row[3],
                "timestamp": row[4].isoformat()
            } for row in rows]
            
            # Cache the results
            try:
                if redis_client:
                    redis_client.setex(
                        cache_key,
                        CACHE_TTL,
                        json.dumps(results)
                    )
            except Exception as e:
                logger.error(f"[TRACE:{trace_id}] Failed to cache results: {str(e)}")
            
            return results
            
    except Exception as e:
        logger.error(f"[TRACE:{trace_id}] Database error: {str(e)}")
        raise HTTPException(
            status_code=503,
            detail={
                "error": "Database error",
                "message": str(e)
            }
        )

@app.get("/weather/aggregate/{station_id}")
def aggregate_weather_data(station_id: str, start_time: str, end_time: str, request: Request):
    trace_id = str(uuid.uuid4())
    logger.info(f"[TRACE:{trace_id}] Aggregate weather data requested for station {station_id}")
    
    try:
        start_dt = datetime.fromisoformat(start_time)
        end_dt = datetime.fromisoformat(end_time)
        logger.info(f"[TRACE:{trace_id}] Date range: {start_time} to {end_time}")
    except ValueError:
        logger.error(f"[TRACE:{trace_id}] Invalid timestamp format")
        raise HTTPException(status_code=400, detail="Invalid timestamp format.")

    # Use TimescaleDB time_bucket for time-series aggregation
    query = """
        SELECT station_id,
               AVG(temperature) AS avg_temperature,
               AVG(humidity) AS avg_humidity,
               AVG(wind_speed) AS avg_wind_speed,
               MIN(temperature) AS min_temperature,
               MAX(temperature) AS max_temperature
        FROM weather
        WHERE station_id = %s AND timestamp BETWEEN %s AND %s
        GROUP BY station_id;
    """
    params = (station_id, start_dt, end_dt)
    key = cache_key(query, params)

    redis_client = get_redis_client()
    if redis_client:
        cached_result = redis_client.get(key)
        if cached_result:
            logger.info(f"[TRACE:{trace_id}] Cache hit for aggregate query")
            result = json.loads(cached_result)
            return result

    conn = get_db_connection()
    if not conn:
        logger.error(f"[TRACE:{trace_id}] Database connection unavailable")
        raise HTTPException(status_code=503, detail="Database connection unavailable")

    try:
        logger.info(f"[TRACE:{trace_id}] Querying database for aggregate data")
        with conn.cursor() as cursor:
            cursor.execute(query, params)
            row = cursor.fetchone()

        if not row:
            logger.warning(f"[TRACE:{trace_id}] No data found for query")
            raise HTTPException(status_code=404, detail="No data found.")

        result = {
            "station_id": row[0],
            "avg_temperature": row[1],
            "avg_humidity": row[2],
            "avg_wind_speed": row[3],
            "min_temperature": row[4],
            "max_temperature": row[5]
        }

        # Cache the result
        if redis_client:
            redis_client.setex(key, CACHE_TTL, json.dumps(result))
            logger.info(f"[TRACE:{trace_id}] Aggregate results cached with key {key}")

        logger.info(f"[TRACE:{trace_id}] Returning aggregate weather data")
        return result
    finally:
        conn.close()

@app.get("/weather/timeseries/{station_id}")
def timeseries_weather_data(
    station_id: str, 
    start_time: str, 
    end_time: str, 
    request: Request,
    interval: str = "1 hour"
):
    """
    Get time-bucketed weather data for a specific time interval.
    
    interval: TimescaleDB time bucket interval (e.g., '1 hour', '30 minutes', '1 day')
    """
    trace_id = str(uuid.uuid4())
    logger.info(f"[TRACE:{trace_id}] TimescaleDB timeseries data requested for station {station_id}")
    
    try:
        start_dt = datetime.fromisoformat(start_time)
        end_dt = datetime.fromisoformat(end_time)
    except ValueError:
        logger.error(f"[TRACE:{trace_id}] Invalid timestamp format")
        raise HTTPException(status_code=400, detail="Invalid timestamp format.")
    
    # Using TimescaleDB time_bucket function
    query = """
        SELECT 
            station_id,
            time_bucket(%s, timestamp) AS bucket,
            AVG(temperature) AS avg_temperature,
            AVG(humidity) AS avg_humidity,
            AVG(wind_speed) AS avg_wind_speed,
            COUNT(*) AS reading_count
        FROM weather
        WHERE station_id = %s AND timestamp BETWEEN %s AND %s
        GROUP BY station_id, bucket
        ORDER BY bucket;
    """
    params = (interval, station_id, start_dt, end_dt)
    key = cache_key(query, params)
    
    redis_client = get_redis_client()
    if redis_client:
        cached_result = redis_client.get(key)
        if cached_result:
            logger.info(f"[TRACE:{trace_id}] Cache hit for timeseries query")
            result = json.loads(cached_result)
            return result

    conn = get_db_connection()
    if not conn:
        logger.error(f"[TRACE:{trace_id}] Database connection unavailable")
        raise HTTPException(status_code=503, detail="Database connection unavailable")

    try:
        logger.info(f"[TRACE:{trace_id}] Querying database for timeseries data")
        with conn.cursor() as cursor:
            cursor.execute(query, params)
            rows = cursor.fetchall()

        if not rows:
            logger.warning(f"[TRACE:{trace_id}] No data found for timeseries query")
            raise HTTPException(status_code=404, detail="No data found.")

        results = [{
            "station_id": row[0],
            "time_bucket": row[1].isoformat(),
            "avg_temperature": row[2],
            "avg_humidity": row[3],
            "avg_wind_speed": row[4],
            "reading_count": row[5]
        } for row in rows]

        # Cache the results
        if redis_client:
            redis_client.setex(key, CACHE_TTL, json.dumps(results))
            logger.info(f"[TRACE:{trace_id}] Timeseries results cached with key {key}")

        logger.info(f"[TRACE:{trace_id}] Returning {len(results)} timeseries buckets")
        return results
    finally:
        conn.close()

if __name__ == "__main__":
    import uvicorn
    logger.info("Starting uvicorn server...")
    # Wait for dependencies to be ready
    max_retries = 5
    retry_delay = 5
    for i in range(max_retries):
        try:
            # Try to connect to both services
            conn = get_db_connection()
            redis_client = get_redis_client()
            if conn and redis_client:
                logger.info("Successfully connected to all dependencies")
                break
            logger.warning(f"Attempt {i+1}/{max_retries}: Some dependencies not ready")
            time.sleep(retry_delay)
        except Exception as e:
            logger.warning(f"Attempt {i+1}/{max_retries}: Error connecting to dependencies: {e}")
            time.sleep(retry_delay)
    
    logger.info("Starting uvicorn server with host=%s, port=%d", HOST, PORT)
    uvicorn.run(app, host=HOST, port=PORT, log_level="info")

