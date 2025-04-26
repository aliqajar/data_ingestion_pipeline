import React, { useState } from 'react';
import {
  Container,
  Paper,
  Typography,
  TextField,
  Button,
  Grid,
  Box,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Alert,
  CircularProgress,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  SelectChangeEvent
} from '@mui/material';
import { DateTimePicker } from '@mui/x-date-pickers/DateTimePicker';
import { LocalizationProvider } from '@mui/x-date-pickers/LocalizationProvider';
import { AdapterDateFns } from '@mui/x-date-pickers/AdapterDateFnsV3'; // Use V3 adapter for date-fns v3

// --- Interfaces for API data ---
interface WeatherData {
  station_id: string;
  temperature: number;
  humidity: number;
  wind_speed: number;
  timestamp: string;
}

interface AggregateData {
  station_id: string;
  avg_temperature: number;
  avg_humidity: number;
  avg_wind_speed: number;
  min_temperature: number;
  max_temperature: number;
}

interface TimeseriesData {
  station_id: string;
  time_bucket: string;
  avg_temperature: number;
  avg_humidity: number;
  avg_wind_speed: number;
  reading_count: number;
}

// --- Component ---
const QueryUI: React.FC = () => {
  // --- State Variables ---
  const [stationId, setStationId] = useState<string>('');
  const [startTime, setStartTime] = useState<Date | null>(new Date(Date.now() - 24 * 60 * 60 * 1000)); // Default: 24 hours ago
  const [endTime, setEndTime] = useState<Date | null>(new Date()); // Default: now
  const [queryType, setQueryType] = useState<'raw' | 'aggregate' | 'timeseries'>('raw');
  const [data, setData] = useState<WeatherData[] | AggregateData | TimeseriesData[] | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [timeseriesInterval, setTimeseriesInterval] = useState<string>('1 hour');

  // --- Event Handlers ---
  const handleQueryTypeChange = (event: SelectChangeEvent<'raw' | 'aggregate' | 'timeseries'>) => {
    setQueryType(event.target.value as 'raw' | 'aggregate' | 'timeseries');
    setData(null); // Clear previous results when query type changes
    setError(null);
  };

  const handleIntervalChange = (event: SelectChangeEvent<string>) => {
    setTimeseriesInterval(event.target.value);
  };

  // --- Data Fetching ---
  const fetchData = async () => {
    if (!stationId || !startTime || !endTime) {
      setError('Please provide Station ID, Start Time, and End Time.');
      return;
    }

    setLoading(true);
    setError(null);
    setData(null); // Clear previous data

    // Construct the API URL based on query type
    const queryServiceBaseUrl = 'http://localhost:8003/weather'; // Ensure this uses port 8003
    let url = '';
    const params = new URLSearchParams({
      start_time: startTime.toISOString(),
      end_time: endTime.toISOString(),
    });

    switch (queryType) {
      case 'raw':
        url = `${queryServiceBaseUrl}/${stationId}?${params.toString()}`;
        break;
      case 'aggregate':
        url = `${queryServiceBaseUrl}/aggregate/${stationId}?${params.toString()}`;
        break;
      case 'timeseries':
        params.append('interval', timeseriesInterval);
        url = `${queryServiceBaseUrl}/timeseries/${stationId}?${params.toString()}`;
        break;
      default:
        setError("Invalid query type selected");
        setLoading(false);
        return;
    }

    console.log(`Fetching data from: ${url}`); // Log the URL for debugging

    try {
      const response = await fetch(url);
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ detail: `HTTP error! status: ${response.status}` }));
        throw new Error(errorData.detail || `HTTP error! status: ${response.status}`);
      }
      const result = await response.json();

      // Handle cases where the API returns an empty array or no data found
      if (Array.isArray(result) && result.length === 0) {
         setData([]); // Set empty array to indicate no data found
         setError("No data found for the specified criteria.");
      } else if (!result || (typeof result === 'object' && Object.keys(result).length === 0)) {
         setData(null); // Set null if the result is empty object
         setError("No data found for the specified criteria.");
      } else {
         setData(result);
      }

    } catch (err) {
      console.error("Fetch error:", err);
      setError(err instanceof Error ? err.message : 'An unknown error occurred while fetching data.');
    } finally {
      setLoading(false);
    }
  };

  // --- Rendering Functions ---
  const renderDataTable = () => {
    if (!Array.isArray(data) || data.length === 0) return null;

    // Dynamically determine headers from the first data object, excluding station_id
    const headers = Object.keys(data[0]).filter(key => key !== 'station_id');

    return (
      <TableContainer component={Paper} sx={{ mt: 2 }}>
        <Table size="small">
          <TableHead>
            <TableRow sx={{ backgroundColor: 'grey.200' }}>
              {headers.map(header => (
                <TableCell key={header} sx={{ fontWeight: 'bold' }}>
                  {/* Format header names (e.g., time_bucket -> Time Bucket) */}
                  {header.split('_').map(word => word.charAt(0).toUpperCase() + word.slice(1)).join(' ')}
                </TableCell>
              ))}
            </TableRow>
          </TableHead>
          <TableBody>
            {data.map((row, index) => (
              <TableRow key={index} hover>
                {headers.map(header => (
                  <TableCell key={header}>
                    {/* Format numbers to 2 decimal places */}
                    {typeof (row as any)[header] === 'number'
                      ? ((row as any)[header] as number).toFixed(2)
                      : (row as any)[header]}
                  </TableCell>
                ))}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>
    );
  };

  const renderAggregateData = () => {
    if (Array.isArray(data) || !data || typeof data !== 'object' || !('station_id' in data)) return null;

    const aggregate = data as AggregateData;
    return (
      <Box sx={{ mt: 2 }}>
        <Typography variant="h6" gutterBottom>Aggregate Results for Station: {aggregate.station_id}</Typography>
        <Grid container spacing={2}>
          {/* Temperature Box */}
          <Grid item xs={12} sm={4}>
            <Paper sx={{ p: 2, textAlign: 'center' }}>
              <Typography variant="subtitle1" gutterBottom>Temperature (°C)</Typography>
              <Typography>Avg: {aggregate.avg_temperature?.toFixed(2) ?? 'N/A'}</Typography>
              <Typography>Min: {aggregate.min_temperature?.toFixed(2) ?? 'N/A'}</Typography>
              <Typography>Max: {aggregate.max_temperature?.toFixed(2) ?? 'N/A'}</Typography>
            </Paper>
          </Grid>
          {/* Humidity Box */}
          <Grid item xs={12} sm={4}>
            <Paper sx={{ p: 2, textAlign: 'center' }}>
              <Typography variant="subtitle1" gutterBottom>Humidity (%)</Typography>
              <Typography>Avg: {aggregate.avg_humidity?.toFixed(2) ?? 'N/A'}</Typography>
            </Paper>
          </Grid>
          {/* Wind Speed Box */}
          <Grid item xs={12} sm={4}>
            <Paper sx={{ p: 2, textAlign: 'center' }}>
              <Typography variant="subtitle1" gutterBottom>Wind Speed (m/s)</Typography>
              <Typography>Avg: {aggregate.avg_wind_speed?.toFixed(2) ?? 'N/A'}</Typography>
            </Paper>
          </Grid>
        </Grid>
      </Box>
    );
  };

  // --- Main Component Return ---
  return (
    // LocalizationProvider needed for DateTimePicker
    <LocalizationProvider dateAdapter={AdapterDateFns}>
      <Container maxWidth="lg">
        <Box sx={{ my: 4 }}>
          <Typography variant="h4" component="h1" gutterBottom>
            Weather Query Interface
          </Typography>

          {/* Input Form */}
          <Paper sx={{ p: 3, mb: 3 }}>
            <Grid container spacing={3} alignItems="center">
              {/* Station ID */}
              <Grid item xs={12} sm={6} md={3}>
                <TextField
                  fullWidth
                  required
                  label="Station ID"
                  value={stationId}
                  onChange={(e) => setStationId(e.target.value)}
                  variant="outlined"
                />
              </Grid>

              {/* Query Type */}
              <Grid item xs={12} sm={6} md={3}>
                <FormControl fullWidth variant="outlined">
                  <InputLabel>Query Type</InputLabel>
                  <Select
                    value={queryType}
                    label="Query Type"
                    onChange={handleQueryTypeChange}
                  >
                    <MenuItem value="raw">Raw Data</MenuItem>
                    <MenuItem value="aggregate">Aggregate</MenuItem>
                    <MenuItem value="timeseries">Timeseries</MenuItem>
                  </Select>
                </FormControl>
              </Grid>

              {/* Timeseries Interval (Conditional) */}
              {queryType === 'timeseries' && (
                <Grid item xs={12} sm={6} md={3}>
                  <FormControl fullWidth variant="outlined">
                    <InputLabel>Interval</InputLabel>
                    <Select
                      value={timeseriesInterval}
                      label="Interval"
                      onChange={handleIntervalChange}
                    >
                      <MenuItem value="15 minutes">15 Minutes</MenuItem>
                      <MenuItem value="30 minutes">30 Minutes</MenuItem>
                      <MenuItem value="1 hour">1 Hour</MenuItem>
                      <MenuItem value="6 hours">6 Hours</MenuItem>
                      <MenuItem value="12 hours">12 Hours</MenuItem>
                      <MenuItem value="1 day">1 Day</MenuItem>
                    </Select>
                  </FormControl>
                </Grid>
              )}

              {/* Start Time */}
               <Grid item xs={12} sm={6} md={queryType === 'timeseries' ? 3 : 3}>
                <DateTimePicker
                  label="Start Time"
                  value={startTime}
                  onChange={(newValue) => setStartTime(newValue)}
                  // renderInput={(params) => <TextField {...params} fullWidth required variant="outlined" />}
                />
              </Grid>

              {/* End Time */}
               <Grid item xs={12} sm={6} md={queryType === 'timeseries' ? 3 : 3}>
                 <DateTimePicker
                  label="End Time"
                  value={endTime}
                  onChange={(newValue) => setEndTime(newValue)}
                   // renderInput={(params) => <TextField {...params} fullWidth required variant="outlined" />}
                />
              </Grid>

              {/* Fetch Button */}
              <Grid item xs={12}>
                <Button
                  variant="contained"
                  onClick={fetchData}
                  disabled={loading || !stationId || !startTime || !endTime}
                  size="large"
                >
                  {loading ? <CircularProgress size={24} /> : 'Fetch Data'}
                </Button>
              </Grid>
            </Grid>
          </Paper>

          {/* Error Display */}
          {error && (
            <Alert severity="error" sx={{ mb: 2 }}>
              {error}
            </Alert>
          )}

          {/* Results Display */}
          {loading && <Box sx={{ display: 'flex', justifyContent: 'center', my: 3 }}><CircularProgress /></Box>}
          {!loading && data && (
            queryType === 'aggregate' ? renderAggregateData() : renderDataTable()
          )}
           {/* Message when no data is returned and no error occurred */}
          {!loading && data === null && !error && (
             <Typography sx={{ mt: 2, fontStyle: 'italic' }}>Submit a query to see results.</Typography>
          )}
           {!loading && Array.isArray(data) && data.length === 0 && !error && (
             <Typography sx={{ mt: 2, fontStyle: 'italic' }}>No data found for the specified criteria.</Typography>
           )}

        </Box>
      </Container>
    </LocalizationProvider>
  );
};

export default QueryUI; 