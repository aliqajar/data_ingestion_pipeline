import React, { useState, useEffect, useCallback } from 'react';
import {
  Container,
  Paper,
  Typography,
  Button,
  Grid,
  Box,
  CircularProgress,
  Alert,
  Switch,
  FormControlLabel,
  TextField,
  Card,
  CardContent,
  Divider,
  SelectChangeEvent
} from '@mui/material';

// --- Interfaces ---
interface GeneratorStatus {
  is_generating: boolean;
  config: {
    interval: number;
    stations: number;
    collector_url: string;
    duplicate_percent: number;
    batch_size: number;
    use_batch: boolean;
    total_generated: number;
    total_duplicates: number;
  };
  total_generated: number;
  total_duplicates: number;
  info: {
    internal_collector_url: string;
    external_collector_url: string;
    batch_mode: boolean;
    batch_info: any;
    note: string;
  };
}

interface StartConfig {
  interval?: number;
  stations?: number;
  collector_url?: string;
  duplicate_percent?: number;
  batch_size?: number;
  use_batch?: boolean;
}

// --- Component ---
const GeneratorUI: React.FC = () => {
  // --- State ---
  const [status, setStatus] = useState<GeneratorStatus | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [actionLoading, setActionLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [pollIntervalId, setPollIntervalId] = useState<NodeJS.Timeout | null>(null);

  // Config state for the start request
  const [config, setConfig] = useState<StartConfig>({
    interval: 1,
    stations: 5,
    collector_url: 'http://localhost:8001/weather-data',
    duplicate_percent: 20,
    batch_size: 10,
    use_batch: true
  });
  const [lastMessagesPerSecond, setLastMessagesPerSecond] = useState<number>(0);
  const [previousTotalGenerated, setPreviousTotalGenerated] = useState<number>(0);
  const [lastPollTime, setLastPollTime] = useState<number | null>(null);
  const [retryCount, setRetryCount] = useState<number>(0);
  const [retryTimer, setRetryTimer] = useState<NodeJS.Timeout | null>(null);

  // Use both localhost and container name to handle different environments
  const generatorUrls = [
    'http://localhost:8004',
    'http://generator:8004',
    'http://host.docker.internal:8004'
  ];
  const [currentUrlIndex, setCurrentUrlIndex] = useState<number>(0);
  const generatorBaseUrl = generatorUrls[currentUrlIndex];

  // --- Fetch Status Function ---
  const fetchStatus = useCallback(async () => {
    // Don't overlap fetches if one is already loading
    if (loading) return;

    setLoading(true);
    try {
      console.log("Fetching generator status from:", `${generatorBaseUrl}/status`);
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 5000); // 5 second timeout
      
      const response = await fetch(`${generatorBaseUrl}/status`, {
        headers: {
          'Accept': 'application/json',
          'Cache-Control': 'no-cache',
          'Content-Type': 'application/json'
        },
        method: 'GET',
        cache: 'no-cache',
        credentials: 'omit',
        signal: controller.signal
      });
      
      clearTimeout(timeoutId);
      
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      
      const data = await response.json();
      console.log("Received status data:", data);
      setRetryCount(0); // Reset retry count on success
      
      // If data doesn't have expected structure, create a default one
      if (!data || !data.config) {
        throw new Error('Invalid response format from generator service');
      }
      
      setStatus(data);

      // Calculate messages per second
      const now = Date.now();
      if (lastPollTime && data.total_generated > previousTotalGenerated) {
        const timeDiffSeconds = (now - lastPollTime) / 1000;
        const messagesDiff = data.total_generated - previousTotalGenerated;
        if (timeDiffSeconds > 0) {
          setLastMessagesPerSecond(Math.round(messagesDiff / timeDiffSeconds));
        } else {
          setLastMessagesPerSecond(0); // Avoid division by zero
        }
      } else if (!data.is_generating) {
         setLastMessagesPerSecond(0); // Reset if not generating
      }

      setPreviousTotalGenerated(data.total_generated || 0);
      setLastPollTime(now);

      // Update config form with values from status
      setConfig(prev => ({
        interval: data.config.interval || prev.interval || 1,
        stations: data.config.stations || prev.stations || 5,
        collector_url: data.config.collector_url || prev.collector_url || 'http://localhost:8001/weather-data',
        duplicate_percent: data.config.duplicate_percent || prev.duplicate_percent || 20,
        batch_size: data.config.batch_size || prev.batch_size || 10,
        use_batch: typeof data.config.use_batch !== 'undefined' ? data.config.use_batch : (prev.use_batch || true),
      }));
      
      setError(null);
    } catch (err) {
      console.error("Fetch status error:", err);
      
      // Try the next URL if this one failed
      if (retryCount >= 2) {
        setCurrentUrlIndex((prevIndex) => (prevIndex + 1) % generatorUrls.length);
        setRetryCount(0);
      } else {
        setRetryCount(prev => prev + 1);
      }
      
      // Show a more helpful error message
      if (err instanceof DOMException && err.name === 'AbortError') {
        setError(`Connection to generator service timed out. Retrying...\nURL: ${generatorBaseUrl}`);
      } else {
        setError(`Failed to connect to generator service (${generatorBaseUrl}). Retrying...`);
      }
      
      // Schedule a retry if not already retrying
      if (!retryTimer) {
        const timer = setTimeout(() => {
          fetchStatus();
          setRetryTimer(null);
        }, 2000);
        setRetryTimer(timer);
      }
    } finally {
      setLoading(false);
    }
  }, [loading, generatorBaseUrl, lastPollTime, previousTotalGenerated, retryCount, retryTimer]); // Add dependencies

  // --- Start/Stop Functions ---
  const handleStart = async () => {
    setActionLoading(true);
    setError(null);
    console.log("Sending start config:", config);
    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 5000); // 5 second timeout
      
      const response = await fetch(`${generatorBaseUrl}/start`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'application/json'
        },
        credentials: 'omit',
        body: JSON.stringify(config), // Send current config state
        signal: controller.signal
      });
      
      clearTimeout(timeoutId);
      
      if (!response.ok) {
        const errorText = await response.text();
        throw new Error(`HTTP error! status: ${response.status}, ${errorText}`);
      }
      
      // Successfully started, fetch status immediately
      await fetchStatus();
      startPolling(); // Ensure polling is active
    } catch (err) {
      console.error("Start error:", err);
      if (err instanceof DOMException && err.name === 'AbortError') {
        setError('Connection timed out while trying to start the generator. Please try again.');
      } else {
        setError(err instanceof Error ? err.message : 'An unknown error occurred while starting.');
      }
    } finally {
      setActionLoading(false);
    }
  };

  const handleStop = async () => {
    setActionLoading(true);
    setError(null);
    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 5000); // 5 second timeout
      
      const response = await fetch(`${generatorBaseUrl}/stop`, {
        method: 'POST',
        headers: {
          'Accept': 'application/json',
          'Content-Type': 'application/json'
        },
        credentials: 'omit',
        signal: controller.signal
      });
      
      clearTimeout(timeoutId);
      
      if (!response.ok) {
        const errorText = await response.text();
        throw new Error(`HTTP error! status: ${response.status}, ${errorText}`);
      }
      
      // Successfully stopped, fetch status immediately and stop polling
      stopPolling();
      await fetchStatus();
      setLastMessagesPerSecond(0); // Explicitly reset rate on stop
    } catch (err) {
      console.error("Stop error:", err);
      if (err instanceof DOMException && err.name === 'AbortError') {
        setError('Connection timed out while trying to stop the generator. Please try again.');
      } else {
        setError(err instanceof Error ? err.message : 'An unknown error occurred while stopping.');
      }
    } finally {
      setActionLoading(false);
    }
  };

  // --- Polling Logic ---
  const startPolling = useCallback(() => {
    // Clear existing interval before starting a new one
    if (pollIntervalId) {
      clearInterval(pollIntervalId);
    }
    // Fetch immediately, then start interval
    fetchStatus();
    const intervalId = setInterval(fetchStatus, 2000); // Poll every 2 seconds
    setPollIntervalId(intervalId);
  }, [fetchStatus, pollIntervalId]); // Include pollIntervalId

  const stopPolling = () => {
    if (pollIntervalId) {
      clearInterval(pollIntervalId);
      setPollIntervalId(null);
    }
  };

  // --- Effects ---
  // Initial fetch and start polling if generator is running
  useEffect(() => {
    console.log("Component mounted, fetching initial status");
    fetchStatus().then(() => {
      // Check initial status after fetch completes
      if (status?.is_generating && !pollIntervalId) {
        startPolling();
      }
    }).catch(err => {
      console.error("Initial fetch error:", err);
    });

    // Cleanup interval on component unmount
    return () => {
      stopPolling();
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []); // Run only once on mount

  // Start/stop polling based on is_generating status from fetches
  useEffect(() => {
    if (status?.is_generating && !pollIntervalId) {
      startPolling();
    } else if (!status?.is_generating && pollIntervalId) {
      stopPolling();
    }
  }, [status?.is_generating, pollIntervalId, startPolling]); // Add dependencies

  // Clean up timers on unmount
  useEffect(() => {
    return () => {
      if (retryTimer) {
        clearTimeout(retryTimer);
      }
    };
  }, [retryTimer]);

  // --- Config Input Handler ---
  const handleConfigChange = (event: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement> | SelectChangeEvent<any>) => {
    const target = event.target;
    const name = target.name as string;
    let value = target.value;
    let type = 'text'; // Default type

    // Check if it's a standard input change event to get the type
    if ('type' in target && typeof target.type === 'string') {
      type = target.type;
    }

    let processedValue: string | number | boolean = value;

    // Handle checkbox/switch based on type
    if (type === 'checkbox' && target instanceof HTMLInputElement) {
      processedValue = target.checked;
    } 
    // Handle numeric fields based on name
    else if (['interval', 'stations', 'duplicate_percent', 'batch_size'].includes(name)) {
      processedValue = value === '' ? '' : parseInt(value, 10);
       // Allow empty string temporarily, handle NaN during start
       if (isNaN(processedValue as number) && value !== '') return; // Prevent non-numeric input for number fields
    }

    setConfig(prev => ({
      ...prev,
      [name]: processedValue,
    }));
  };

  // --- Render Helper Functions ---
  const renderStatusCard = () => {
    return (
      <Card variant="outlined" sx={{ minWidth: 275, mb: 2 }}>
        <CardContent>
          <Typography variant="h6" component="div" sx={{ mb: 1 }}>
            Status
          </Typography>
          {loading && !status ? (
            <Box sx={{ display: 'flex', justifyContent: 'center', my: 2 }}>
              <CircularProgress size={24} />
            </Box>
          ) : status ? (
            <>
              <Typography color="text.secondary" gutterBottom>
                Generator is {status.is_generating ? 'running' : 'stopped'}
              </Typography>
              <Typography variant="body2">
                Total records: {status.total_generated || 0}
              </Typography>
              <Typography variant="body2">
                Duplicates: {status.total_duplicates || 0} ({status.total_generated ? Math.round((status.total_duplicates / status.total_generated) * 100) : 0}%)
              </Typography>
              <Typography variant="body2">
                Throughput: {lastMessagesPerSecond} records/sec
              </Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mt: 1, fontSize: '0.8rem' }}>
                Connected to: {generatorBaseUrl}
              </Typography>
            </>
          ) : (
            <Typography color="text.secondary">
              No status data available. Trying to connect to generator service...
            </Typography>
          )}
          {error && (
            <Alert severity="error" sx={{ mt: 2 }}>
              {error}
            </Alert>
          )}
          <Box sx={{ mt: 2 }}>
            <Button 
              variant="outlined" 
              onClick={fetchStatus} 
              disabled={loading}
              size="small"
              sx={{ mr: 1 }}
            >
              {loading ? <CircularProgress size={20} /> : 'Refresh Status'}
            </Button>
            <Button
              variant="text"
              size="small"
              onClick={() => setCurrentUrlIndex((prevIndex) => (prevIndex + 1) % generatorUrls.length)}
              disabled={loading}
            >
              Try Different URL
            </Button>
          </Box>
        </CardContent>
      </Card>
    );
  };

  const renderActionButtons = () => {
    return (
      <Box sx={{ mt: 2, display: 'flex', justifyContent: 'space-between' }}>
        <Button
          variant="contained"
          color="primary"
          onClick={handleStart}
          disabled={actionLoading || (status?.is_generating === true)}
          sx={{ mr: 2 }}
        >
          {actionLoading ? <CircularProgress size={24} /> : 'Start Generator'}
        </Button>
        <Button
          variant="contained"
          color="secondary"
          onClick={handleStop}
          disabled={actionLoading || (status?.is_generating === false)}
        >
          {actionLoading ? <CircularProgress size={24} /> : 'Stop Generator'}
        </Button>
      </Box>
    );
  };

  const renderConfigForm = () => {
    return (
      <Card variant="outlined" sx={{ minWidth: 275, mb: 3 }}>
        <CardContent>
          <Typography variant="h6" component="div" sx={{ mb: 2 }}>
            Generator Configuration
          </Typography>
          <Grid container spacing={2}>
            <Grid item xs={12} sm={6}>
              <TextField
                fullWidth
                label="Interval (seconds)"
                name="interval"
                type="number"
                value={config.interval ?? ''}
                onChange={handleConfigChange}
                variant="outlined"
                size="small"
                InputProps={{ inputProps: { min: 1 } }}
              />
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField
                fullWidth
                label="Number of Stations"
                name="stations"
                type="number"
                value={config.stations ?? ''}
                onChange={handleConfigChange}
                variant="outlined"
                size="small"
                InputProps={{ inputProps: { min: 1 } }}
              />
            </Grid>
            <Grid item xs={12}>
              <TextField
                fullWidth
                label="Collector URL"
                name="collector_url"
                value={config.collector_url ?? ''}
                onChange={handleConfigChange}
                variant="outlined"
                size="small"
                placeholder="http://localhost:8001/weather-data"
              />
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField
                fullWidth
                label="Duplicate Percentage"
                name="duplicate_percent"
                type="number"
                value={config.duplicate_percent ?? ''}
                onChange={handleConfigChange}
                variant="outlined"
                size="small"
                InputProps={{ inputProps: { min: 0, max: 100 } }}
              />
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField
                fullWidth
                label="Batch Size"
                name="batch_size"
                type="number"
                value={config.batch_size ?? ''}
                onChange={handleConfigChange}
                variant="outlined"
                size="small"
                InputProps={{ inputProps: { min: 1 } }}
                disabled={!config.use_batch}
              />
            </Grid>
            <Grid item xs={12}>
              <FormControlLabel
                control={
                  <Switch
                    checked={config.use_batch ?? false}
                    onChange={handleConfigChange}
                    name="use_batch"
                  />
                }
                label="Use Batch Mode"
              />
            </Grid>
          </Grid>
          {renderActionButtons()}
        </CardContent>
      </Card>
    );
  };

  return (
    <Container maxWidth="md" sx={{ py: 4 }}>
      <Paper elevation={3} sx={{ p: 3 }}>
        <Typography variant="h4" component="h1" gutterBottom>
          Data Generator Control
        </Typography>
        <Typography variant="body1" paragraph>
          Configure and control the weather data generation process.
        </Typography>
        <Divider sx={{ my: 2 }} />

        {renderStatusCard()}
        {renderConfigForm()}

      </Paper>
    </Container>
  );
};

export default GeneratorUI; 