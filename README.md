# Weather System Pipeline

A high-performance weather data ingestion and query system built with FastAPI, Kafka, PostgreSQL (TimescaleDB), and Redis.

## Quick Start

### Prerequisites
- Docker
- Docker Compose

### Running the System
For first-time setup, build all services before starting them:
```bash
docker compose build
docker compose up -d
```

For subsequent runs, you can simply use:
```bash
docker compose up -d
```

### Running Tests
Execute all tests:
```bash
docker compose run --rm test
```

## Assumptions

This system was designed with the following assumptions:

### Data Format
- Weather data follows a format similar to NOAA endpoints
- Key fields include station_id, temperature, humidity, wind_speed, and timestamp
- Timestamp is in ISO 8601 format (YYYY-MM-DDTHH:MM:SSZ)

### Data Ingestion
- System supports both individual data point ingestion and batch processing
- Single-point endpoint: `/weather-data` for individual readings
  - Optimized for real-time, low-latency data submission
  - Suitable for stations with reliable, continuous connectivity
  - Each request processes one weather data point independently
- Batch endpoint: `/weather-data/batch` for submitting multiple readings simultaneously
  - Designed for efficiency in transmitting multiple records in a single HTTP request
  - Ideal for stations with intermittent connectivity or bandwidth constraints
  - Reduces network overhead for stations that collect readings over time before transmission
  - Provides detailed results on success/failure of each record in the batch
- The system can handle and deduplicate data regardless of ingestion method
- Both endpoints share the same validation and processing pipeline, ensuring consistent data quality

### Data Partitioning
- Data is primarily partitioned by station_id
- The composite key (station_id, timestamp) is used for efficient querying
- This structure optimizes for time-series queries for specific stations

### Scalability Considerations
- No sharding is currently implemented
- Future horizontal sharding could be based on geographical locations if data ingestion increases significantly
- The system is designed to scale horizontally by adding more instances of each service

### Real-time vs Batch Processing
- The system prioritizes near real-time processing
- Some delay (seconds to minutes) is acceptable
- Data consistency is prioritized over absolute real-time delivery

## System Design

This system implements at-least-once semantics, optimized for high-throughput data ingestion. The architecture ensures:
- Reliable data ingestion through Kafka's at-least-once delivery guarantee
- In-memory deduplication in the Consumer service
- Additional deduplication during database insertion using TimescaleDB's unique constraints
- Efficient time-series data storage using TimescaleDB extension, optimized for large-scale time-series data ingestion and querying

### Architecture Diagram
To view the system architecture, see the flowchart in `Weather Data Ingestion.png`. To add this diagram to the README, move the file to the `docs` directory and update the reference as follows:

![Weather Data Ingestion Pipeline](Weather_Data_Ingestion.png)


## API Documentation
When the system is running, access the API documentation at:
- Collector Service: http://localhost:8001/docs
- Consumer Service: http://localhost:8002/docs
- Query Service: http://localhost:8003/docs
- Generator Service: http://localhost:8004/docs

### Service API Overviews

#### Generator Service
The Generator Service simulates weather stations and sends data to the Collector Service. It provides endpoints to start and stop data generation.

![Generator Service API](Generator.png)

#### Collector Service
The Collector Service receives weather data from stations (or the Generator), validates it, and publishes it to Kafka. It includes endpoints for data ingestion and health monitoring.

![Collector Service API](Collector.png)

#### Consumer Service
The Consumer Service reads data from Kafka, processes it for deduplication, and stores it in the TimescaleDB database. It provides endpoints to view consumer statistics and health status.

![Consumer Service API](Consumer.png)

#### Query Service
The Query Service retrieves data from the database and provides endpoints for querying raw weather data, aggregated statistics, and time-series analysis.

![Query Service API](Query.png)

## Using the System

### 1. Generate Test Data

The system includes a data generator service to simulate weather stations sending data:

1. Access the Generator Service documentation at http://localhost:8004/docs
2. Use the `/start` endpoint to begin generating data. You can configure:
   - `interval`: Time between data generation cycles (in seconds)
   - `stations`: Number of weather stations to simulate
   - `use_batch`: Set to true to use batch data submission (default: true)
   - `batch_size`: Number of records to send in each batch (default: 5)
   - `collector_url`: URL of the collector service
   - `duplicate_percent`: Percentage of duplicate data for testing deduplication (default: 20%)

   ![Starting the data generator](Weather_Start.png)

3. After generating enough data (a few seconds is usually sufficient), use the `/stop` endpoint to stop the generator.

4. You can check the generator status using the `/status` endpoint to see statistics about the data generation process.

### 2. Query the Data

Once data has been generated and processed, you can query it using the Query Service:

1. Access the Query Service documentation at http://localhost:8003/docs
2. Use the `/weather/{station_id}` endpoint to retrieve weather data for a specific station. You can optionally provide start_time and end_time parameters to filter by date range.

   ![Querying weather data](Weather_Query.png)

3. The API will return all weather data for the requested station, ordered by timestamp.

### 3. Advanced Querying

The Query Service also provides advanced data retrieval endpoints:

1. **Aggregate Data**: Use `/weather/aggregate/{station_id}` to get statistical summaries (min, max, average) of weather measurements for a specific station and time range.

2. **Time-series Analysis**: Use `/weather/timeseries/{station_id}` to get time-bucketed data aggregations. This uses TimescaleDB's time_bucket function to group data into intervals, allowing for trend analysis.

## Monitoring

### View Service Logs
```bash
# View collector logs
docker compose logs collector -f

# View consumer logs
docker compose logs consumer -f

# View query service logs
docker compose logs query -f
```

### Logging and Monitoring
The system uses structured logging compatible with Datadog agents. All logs include:
- Trace IDs for request tracking
- Service name
- Log level
- Timestamp

When Datadog agents are installed, they can automatically collect these logs for:
- Distributed tracing
- Performance monitoring
- Error tracking
- Metrics visualization 

## Troubleshooting

### Consumer Service Kafka Connection Issues

If you see errors like these in the consumer logs:
```
ERROR:aiokafka.consumer.group_coordinator:Error sending JoinGroupRequest_v5 to node 1 [[Error 7] RequestTimedOutError]
WARNING:aiokafka.cluster:Topic weather_data is not available during auto-create initialization
```

These indicate that the consumer is having trouble connecting to Kafka. Here's how to fix it:

1. **Ensure Kafka is fully initialized**:
   ```bash
   docker compose logs kafka | grep "started"
   ```
   You should see a message indicating Kafka has started successfully.

2. **Restart the consumer service**:
   ```bash
   docker compose restart consumer
   ```

3. **Create the topic manually** (if it doesn't exist):
   ```bash
   docker compose exec kafka kafka-topics --create --topic weather_data --bootstrap-server localhost:9092 --partitions 1 --replication-factor 1
   ```

4. **Verify the topic exists**:
   ```bash
   docker compose exec kafka kafka-topics --list --bootstrap-server localhost:9092
   ```

### No Data Appearing in Query Results

If you've generated data but nothing appears in your query results:

1. **Check if consumer is processing messages**:
   ```bash
   docker compose logs consumer | grep "Processing message"
   ```
   
2. **Verify data is in the database**:
   ```bash
   docker compose exec postgres psql -U weather_user -d weather_db -c "SELECT COUNT(*) FROM weather;"
   ```

3. **Generate more data** with the generator service if needed.

## Considered but Not Implemented

For the purpose of this demo, several advanced features were considered but not implemented to maintain simplicity and clarity:

### Security Considerations
- **SSL Termination**: In a production environment, all services would be placed behind a load balancer with SSL termination
- **Security in Transit**: HTTPS would be enabled for all external communication
- **Database Security**: Since weather data is not considered highly sensitive, encryption at rest was deemed unnecessary
- **Network Isolation**: In a production environment, internal services would be placed in private subnets with no direct external access
- **API Authentication**: Token-based authentication would be implemented for the collector API in production
- **Role-Based Access Control**: Different permission levels would be established for different API endpoints

### Push vs Pull Model
- Current implementation uses a **Push Model** where weather stations send data to our collector service
- A **Pull Model** would be more efficient in production, where our system would:
  - Use service discovery (e.g., Consul, etcd) to maintain registry of weather stations
  - Implement Kubernetes for pod management and scaling
  - Actively poll weather stations at configured intervals
  - Better handle station failures and network issues
  - Allow for more controlled data ingestion rates
- Pull model was not implemented to align with the initial requirements and keep the demo infrastructure simpler

### Load Testing
- **k6** would be ideal for end-to-end load testing of this system:
  - Can simulate multiple weather stations pushing data
  - Supports WebSocket and HTTP protocols
  - Allows testing different load patterns
  - Provides detailed performance metrics
  - Can integrate with CI/CD pipelines
- Not implemented to keep the demo focused on core functionality

### Load Balancer Enhancements
- **Rate Limiting**: Could prevent abuse and ensure fair resource distribution
- **SSL Termination**: Would add HTTPS support at the load balancer level
- **Advanced Health Checks**: More sophisticated service health monitoring
- **Circuit Breakers**: Would help prevent cascading failures

### API Design Considerations
- **GraphQL vs REST**: Considered implementing GraphQL for the query service
  - GraphQL would offer greater flexibility for clients to request exactly the data they need
  - However, REST was chosen for better maintainability and simpler implementation
  - GraphQL would increase complexity for caching and monitoring
  - The structured nature of weather data fits well with REST resource patterns
  - REST endpoints are more compatible with typical time-series data access patterns

### Query Service Optimizations
- **Cursor-based Pagination**: Would improve handling of large datasets using timestamp-based cursors
- **Async Job System**: For handling long-running queries without blocking
- **Query Timeouts**: To prevent long-running queries from consuming resources
- **Advanced Caching Strategies**: More sophisticated cache invalidation and warming

### Data Management
- **Data Retention Policies**: Automated cleanup of old time-series data
- **Continuous Aggregates**: Pre-calculated aggregations for common time windows
- **Partitioning Strategies**: Advanced TimescaleDB chunk management

These features would be valuable in a production environment but were omitted to keep the demo focused and maintainable. 

## Usage

### API Examples

#### Individual Data Point Submission
Send a single weather data point to the collector service:

```bash
curl -X POST http://localhost:8000/weather-data \
  -H "Content-Type: application/json" \
  -d '{
    "station_id": "STATION123",
    "temperature": 25.5,
    "humidity": 65.2,
    "wind_speed": 15.7,
    "timestamp": "2023-04-15T14:30:00Z"
  }'
```

#### Batch Data Submission
Send multiple weather data points in a single request:

```bash
curl -X POST http://localhost:8000/weather-data/batch \
  -H "Content-Type: application/json" \
  -d '{
    "batch_id": "BATCH-001",
    "records": [
      {
        "station_id": "STATION123",
        "temperature": 25.5,
        "humidity": 65.2,
        "wind_speed": 15.7,
        "timestamp": "2023-04-15T14:30:00Z"
      },
      {
        "station_id": "STATION456",
        "temperature": 22.3,
        "humidity": 70.1,
        "wind_speed": 10.5,
        "timestamp": "2023-04-15T14:30:00Z"
      }
    ]
  }'
```

The batch endpoint returns a summary of the processing results:
```json
{
  "status": "completed",
  "batch_id": "BATCH-001",
  "total": 2,
  "successful": 2,
  "failed": 0,
  "failures": []
}
```

#### Querying Data
Query weather data for a specific station:

```bash
curl -X GET http://localhost:8003/weather/{station_id}
```

Replace `{station_id}` with the actual station ID you want to query.

## Testing

The system includes both unit tests and integration tests to ensure functionality is working correctly.

### Test Types

- **Unit Tests**: Test individual components in isolation, mocking dependencies
- **Integration Tests**: Test components with actual dependencies (Kafka, PostgreSQL, etc.)

### Running Tests

Run all tests (unit and integration):

```bash
docker compose run --rm test
```

Run tests for a specific service:

```bash
docker compose run --rm test python -m pytest services/collector/
docker compose run --rm test python -m pytest services/query/
```

Run specific test files:

```bash
docker compose run --rm test python -m pytest services/collector/tests/test_collector.py -v
docker compose run --rm test python -m pytest services/query/tests/test_query_integration.py -v
```

### Integration Tests

Integration tests are designed to be resilient to temporary unavailability of dependencies. Tests will:

1. Check if required services (database, Redis, etc.) are available
2. Skip tests that depend on unavailable services
3. Test REST endpoints without depending on message broker functionality

This approach ensures tests can run in environments where some dependencies might not be fully available or properly configured. 