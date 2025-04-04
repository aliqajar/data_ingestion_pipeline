import random
import time
import asyncio
import aiohttp
import json
import uuid
import os
import logging
from datetime import datetime
from fastapi import FastAPI, BackgroundTasks, HTTPException
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

load_dotenv()

app = FastAPI(title="Weather Data Generator Service")

# Service configuration
PORT = int(os.getenv('GENERATOR_PORT', '8004'))
HOST = os.getenv('HOST', '0.0.0.0')
DEFAULT_COLLECTOR_URL = os.getenv('COLLECTOR_URL', 'http://collector:8000/weather-data')
DEFAULT_INTERVAL = int(os.getenv('GENERATOR_INTERVAL', '1'))
DEFAULT_STATION_COUNT = int(os.getenv('GENERATOR_STATIONS', '3'))

logger.info(f"Starting Generator service on {HOST}:{PORT}")
logger.info(f"Default collector URL: {DEFAULT_COLLECTOR_URL}")

# Global state
generator_task = None
is_generating = False
generation_config = {
    "interval": DEFAULT_INTERVAL,
    "stations": DEFAULT_STATION_COUNT,
    "collector_url": DEFAULT_COLLECTOR_URL,
    "total_generated": 0,
    "total_duplicates": 0  # Track total duplicates generated
}

class GeneratorConfig(BaseModel):
    interval: Optional[int] = 1
    stations: Optional[int] = DEFAULT_STATION_COUNT
    collector_url: Optional[str] = DEFAULT_COLLECTOR_URL
    duplicate_percent: Optional[int] = 20  # Percentage of data that should be duplicates for testing

def generate_weather_data(station_id):
    """Generate random weather data for a station"""
    trace_id = str(uuid.uuid4())
    data = {
        "station_id": f"station{station_id}",
        "temperature": round(random.uniform(-10, 35), 1),  # Celsius
        "humidity": round(random.uniform(0, 100), 1),  # Percentage
        "wind_speed": round(random.uniform(0, 30), 1),  # km/h
        "timestamp": datetime.now().isoformat(),
        "trace_id": trace_id  # Add trace ID for tracking
    }
    logger.info(f"[TRACE:{trace_id}] Generated weather data: {data}")
    return data

async def send_data(url, data, trace_id):
    """Send data to the collector service"""
    try:
        # Add trace ID to headers for distributed tracing
        headers = {
            "X-Trace-ID": trace_id,
            "Content-Type": "application/json"
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=data, headers=headers, timeout=5) as response:
                if response.status == 200:
                    logger.info(f"[TRACE:{trace_id}] Successfully sent data for {data['station_id']}")
                    return True
                else:
                    logger.error(f"[TRACE:{trace_id}] Failed to send data: {response.status}")
                    return False
    except Exception as e:
        logger.error(f"[TRACE:{trace_id}] Unexpected error in send_data: {e}")
        return False

async def generate_data_task():
    """Background task to generate data"""
    global is_generating, generation_config
    
    logger.info(f"Starting data generation task with interval={generation_config['interval']}s, stations={generation_config['stations']}")
    
    # Store recent data for duplication
    recent_data = []
    duplicate_percent = generation_config.get('duplicate_percent', 20)
    
    # Simple counter for predictable duplicates
    record_count = 0
    
    try:
        while is_generating:
            tasks = []
            
            # Generate regular data for all stations
            for station_id in range(1, generation_config['stations'] + 1):
                if not is_generating:
                    break
                
                record_count += 1
                
                # Every 5th record (20%) will be a duplicate instead of new data
                if len(recent_data) > 0 and record_count % 5 == 0:
                    # Create a duplicate
                    dup_data, dup_trace_id = random.choice(recent_data)
                    new_trace_id = str(uuid.uuid4())
                    
                    logger.info(f"[TRACE:{new_trace_id}] DUPLICATE TEST: Sending duplicate data for {dup_data['station_id']} at {dup_data['timestamp']}")
                    generation_config['total_duplicates'] += 1
                    
                    # Send duplicate with new trace ID
                    dup_data_copy = dup_data.copy()
                    dup_data_copy['trace_id'] = new_trace_id
                    
                    task = asyncio.create_task(send_data(generation_config['collector_url'], dup_data_copy, new_trace_id))
                    tasks.append(task)
                    generation_config['total_generated'] += 1
                else:
                    # Generate new data
                    data = generate_weather_data(station_id)
                    
                    # Store for potential duplication
                    recent_data.append((data, data['trace_id']))
                    if len(recent_data) > 10:
                        recent_data.pop(0)  # Keep buffer size reasonable
                    
                    # Send data
                    task = asyncio.create_task(send_data(generation_config['collector_url'], data, data['trace_id']))
                    tasks.append(task)
                    generation_config['total_generated'] += 1
            
            # Wait for all send operations to complete
            if tasks:
                await asyncio.gather(*tasks)
            
            # Log stats every batch
            percent = (generation_config['total_duplicates'] / generation_config['total_generated']) * 100 if generation_config['total_generated'] > 0 else 0
            logger.info(f"STATS: {generation_config['total_duplicates']} duplicates out of {generation_config['total_generated']} records ({percent:.1f}%)")
            
            # Sleep for the configured interval
            await asyncio.sleep(generation_config['interval'])
    except Exception as e:
        logger.error(f"Error in generate_data_task: {e}")
        is_generating = False

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    trace_id = str(uuid.uuid4())
    logger.info(f"[TRACE:{trace_id}] Health check requested")
    return {
        "status": "healthy",
        "service": "generator",
        "generating": is_generating,
        "trace_id": trace_id,
        "config": generation_config
    }

@app.post("/start")
async def start_generation(config: GeneratorConfig, background_tasks: BackgroundTasks):
    """Start generating data with the given configuration"""
    global generator_task, is_generating, generation_config
    
    # Respond immediately even if already running
    already_running = is_generating
    
    # Update configuration (do this even if already running to allow config changes)
    if config.interval is not None:
        generation_config['interval'] = config.interval
    if config.stations is not None:
        generation_config['stations'] = config.stations
    if config.collector_url is not None:
        generation_config['collector_url'] = config.collector_url
    if config.duplicate_percent is not None:
        generation_config['duplicate_percent'] = config.duplicate_percent
        
    logger.info(f"Configured to generate {generation_config['duplicate_percent']}% duplicate records for testing")
    
    if not already_running:
        is_generating = True
        generation_config['total_generated'] = 0
        generation_config['total_duplicates'] = 0  # Reset duplicate counter
        # Use create_task instead of background_tasks for better control
        asyncio.create_task(generate_data_task())
        logger.info(f"Started data generation with config: {generation_config}")
        return {"status": "started", "message": "Data generation started", "config": generation_config}
    else:
        logger.info(f"Updated configuration for running generator: {generation_config}")
        return {"status": "already_running", "message": "Data generation already running, updated config", "config": generation_config}

@app.post("/stop")
async def stop_generation():
    """Stop generating data"""
    global is_generating, generation_config
    
    # Respond immediately regardless of current state
    was_running = is_generating
    is_generating = False
    total_generated = generation_config['total_generated']
    total_duplicates = generation_config['total_duplicates']
    
    if was_running:
        logger.info(f"Stopping data generation. Generated {total_generated} data points, including {total_duplicates} duplicates.")
        return {
            "status": "stopping", 
            "message": "Data generation is stopping", 
            "total_generated": total_generated,
            "total_duplicates": total_duplicates,
            "config": generation_config
        }
    else:
        return {"status": "not_running", "message": "Data generation was not running"}

@app.get("/status")
async def get_status():
    """Get the current generation status"""
    # Calculate external URL based on internal URL
    internal_url = generation_config['collector_url'] 
    external_url = internal_url.replace("collector:8000", "localhost:8001")
    
    return {
        "is_generating": is_generating,
        "config": generation_config,
        "total_generated": generation_config['total_generated'],
        "total_duplicates": generation_config['total_duplicates'],
        "info": {
            "internal_collector_url": internal_url,  # URL for Docker internal network
            "external_collector_url": external_url,  # URL for accessing from host machine
            "note": "The service uses internal_collector_url for Docker networking"
        }
    }

if __name__ == "__main__":
    import uvicorn
    logger.info(f"Starting uvicorn server on {HOST}:{PORT}")
    uvicorn.run(app, host=HOST, port=PORT) 