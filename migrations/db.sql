-- Enable TimescaleDB extension
CREATE EXTENSION IF NOT EXISTS timescaledb;

-- Create the weather table
CREATE TABLE weather (
    station_id TEXT NOT NULL,
    temperature FLOAT NOT NULL,
    humidity FLOAT NOT NULL,
    wind_speed FLOAT NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (station_id, timestamp)
);

-- Create TimescaleDB hypertable for efficient time-series operations
SELECT create_hypertable('weather', 'timestamp');

-- Create index for efficient querying
CREATE INDEX IF NOT EXISTS idx_weather_station_time ON weather (station_id, timestamp DESC);

-- Stored procedure for inserting weather data
CREATE OR REPLACE PROCEDURE insert_weather_data(
    p_station_id TEXT,
    p_temperature FLOAT,
    p_humidity FLOAT,
    p_wind_speed FLOAT,
    p_timestamp TIMESTAMPTZ
)
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO weather (station_id, temperature, humidity, wind_speed, timestamp)
    VALUES (p_station_id, p_temperature, p_humidity, p_wind_speed, p_timestamp)
    ON CONFLICT (station_id, timestamp) DO NOTHING;
END;
$$;

-- Stored procedure for getting weather data by station and time range
CREATE OR REPLACE PROCEDURE get_weather_data_by_station(
    p_station_id TEXT,
    p_start_time TIMESTAMPTZ,
    p_end_time TIMESTAMPTZ,
    OUT result_cursor REFCURSOR
)
LANGUAGE plpgsql
AS $$
BEGIN
    OPEN result_cursor FOR
    SELECT w.station_id, w.temperature, w.humidity, w.wind_speed, w.timestamp
    FROM weather w
    WHERE w.station_id = p_station_id
    AND w.timestamp BETWEEN p_start_time AND p_end_time
    ORDER BY w.timestamp DESC;
END;
$$;

-- Stored procedure for getting aggregated weather data
CREATE OR REPLACE PROCEDURE get_aggregated_weather_data(
    p_station_id TEXT,
    p_start_time TIMESTAMPTZ,
    p_end_time TIMESTAMPTZ,
    OUT result_cursor REFCURSOR
)
LANGUAGE plpgsql
AS $$
BEGIN
    OPEN result_cursor FOR
    SELECT 
        w.station_id,
        AVG(w.temperature)::FLOAT AS avg_temperature,
        AVG(w.humidity)::FLOAT AS avg_humidity,
        AVG(w.wind_speed)::FLOAT AS avg_wind_speed
    FROM weather w
    WHERE w.station_id = p_station_id
    AND w.timestamp BETWEEN p_start_time AND p_end_time
    GROUP BY w.station_id;
END;
$$;

-- Stored procedure for getting latest weather data for all stations
CREATE OR REPLACE PROCEDURE get_latest_weather_data(
    OUT result_cursor REFCURSOR
)
LANGUAGE plpgsql
AS $$
BEGIN
    OPEN result_cursor FOR
    SELECT DISTINCT ON (w.station_id) 
        w.station_id, w.temperature, w.humidity, w.wind_speed, w.timestamp
    FROM weather w
    ORDER BY w.station_id, w.timestamp DESC;
END;
$$; 