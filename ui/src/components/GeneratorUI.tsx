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
  const [config, setConfig] = useState<StartConfig>({});
  const [lastMessagesPerSecond, setLastMessagesPerSecond] = useState<number>(0);
  const [previousTotalGenerated, setPreviousTotalGenerated] = useState<number>(0);
  const [lastPollTime, setLastPollTime] = useState<number | null>(null);

  const generatorBaseUrl = 'http://localhost:8004'; // Default generator port

  // --- Fetch Status Function ---
  const fetchStatus = useCallback(async () => {
    // Don't overlap fetches if one is already loading
    if (loading) return;

    setLoading(true);
    setError(null);
    try {
      const response = await fetch(`${generatorBaseUrl}/status`);
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ detail: `HTTP error! status: ${response.status}` }));
        throw new Error(errorData.detail || `HTTP error! status: ${response.status}`);
      }
      const data: GeneratorStatus = await response.json();
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

      setPreviousTotalGenerated(data.total_generated);
      setLastPollTime(now);

      // Update config form if status provides defaults we don't have
      setConfig(prev => ({
        interval: prev.interval ?? data.config.interval,
        stations: prev.stations ?? data.config.stations,
        collector_url: prev.collector_url ?? data.info.external_collector_url, // Use external for UI display/input
        duplicate_percent: prev.duplicate_percent ?? data.config.duplicate_percent,
        batch_size: prev.batch_size ?? data.config.batch_size,
        use_batch: prev.use_batch ?? data.config.use_batch,
      }));

    } catch (err) {
      console.error("Fetch status error:", err);
      setError(err instanceof Error ? err.message : 'An unknown error occurred while fetching status.');
      setStatus(null); // Clear status on error
      setLastMessagesPerSecond(0);
    } finally {
      setLoading(false);
    }
  }, [loading, generatorBaseUrl, lastPollTime, previousTotalGenerated]); // Add dependencies

  // --- Start/Stop Functions ---
  const handleStart = async () => {
    setActionLoading(true);
    setError(null);
    console.log("Sending start config:", config);
    try {
      const response = await fetch(`${generatorBaseUrl}/start`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(config), // Send current config state
      });
      if (!response.ok) {
         const errorData = await response.json().catch(() => ({ detail: `HTTP error! status: ${response.status}` }));
        throw new Error(errorData.detail || `HTTP error! status: ${response.status}`);
      }
      // Successfully started, fetch status immediately
      await fetchStatus();
      startPolling(); // Ensure polling is active
    } catch (err) {
      console.error("Start error:", err);
      setError(err instanceof Error ? err.message : 'An unknown error occurred while starting.');
    } finally {
      setActionLoading(false);
    }
  };

  const handleStop = async () => {
    setActionLoading(true);
    setError(null);
    try {
      const response = await fetch(`${generatorBaseUrl}/stop`, {
        method: 'POST',
      });
      if (!response.ok) {
         const errorData = await response.json().catch(() => ({ detail: `HTTP error! status: ${response.status}` }));
        throw new Error(errorData.detail || `HTTP error! status: ${response.status}`);
      }
       // Successfully stopped, fetch status immediately and stop polling
      stopPolling();
      await fetchStatus();
      setLastMessagesPerSecond(0); // Explicitly reset rate on stop

    } catch (err) {
      console.error("Stop error:", err);
      setError(err instanceof Error ? err.message : 'An unknown error occurred while stopping.');
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
    fetchStatus().then(() => {
      // Check initial status after fetch completes
      setStatus(currentStatus => {
        if (currentStatus?.is_generating && !pollIntervalId) {
          startPolling();
        }
        return currentStatus; // Return the state for setStatus
      });
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
    // No cleanup function here, managed by mount/unmount effect
  }, [status?.is_generating, pollIntervalId, startPolling, stopPolling]); // Add stopPolling to dependency array

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

  // --- Render ---
  return (
    <Container maxWidth="md">
      <Box sx={{ my: 4 }}>
        <Typography variant="h4" component="h1" gutterBottom>
          Data Generator Control
        </Typography>

        {/* Error Display */}
        {error && (
          <Alert severity="error" sx={{ mb: 2 }}>
            {error}
          </Alert>
        )}

        <Grid container spacing={3}>
          {/* Control Panel */}
          <Grid item xs={12} md={5}>
            <Paper sx={{ p: 2, display: 'flex', flexDirection: 'column', gap: 2 }}>
              <Typography variant="h6">Controls</Typography>
              <Box sx={{ display: 'flex', gap: 2 }}>
                <Button
                  variant="contained"
                  color="primary"
                  onClick={handleStart}
                  disabled={actionLoading || status?.is_generating}
                  startIcon={actionLoading ? <CircularProgress size={20} color="inherit" /> : null}
                >
                  Start
                </Button>
                <Button
                  variant="contained"
                  color="secondary"
                  onClick={handleStop}
                  disabled={actionLoading || !status?.is_generating}
                  startIcon={actionLoading ? <CircularProgress size={20} color="inherit" /> : null}
                >
                  Stop
                </Button>
              </Box>
              <Divider sx={{ my: 1 }} />
              <Typography variant="h6">Configuration</Typography>
              <TextField
                  label="Interval (seconds)"
                  name="interval"
                  type="number"
                  value={config.interval ?? ''}
                  onChange={handleConfigChange}
                  size="small"
                  inputProps={{ min: 0 }}
              />
              <TextField
                  label="Number of Stations"
                  name="stations"
                  type="number"
                  value={config.stations ?? ''}
                  onChange={handleConfigChange}
                  size="small"
                  inputProps={{ min: 1 }}
              />
               <TextField
                  label="Collector URL"
                  name="collector_url"
                  value={config.collector_url ?? ''}
                  onChange={handleConfigChange}
                  size="small"
              />
               <TextField
                  label="Duplicate %"
                  name="duplicate_percent"
                  type="number"
                  value={config.duplicate_percent ?? ''}
                  onChange={handleConfigChange}
                  size="small"
                  inputProps={{ min: 0, max: 100 }}
              />
              <FormControlLabel
                control={<Switch checked={config.use_batch ?? false} onChange={handleConfigChange} name="use_batch" />}
                label="Use Batch Sending"
              />
               {config.use_batch && (
                <TextField
                    label="Batch Size"
                    name="batch_size"
                    type="number"
                    value={config.batch_size ?? ''}
                    onChange={handleConfigChange}
                    size="small"
                    inputProps={{ min: 1 }}
                />
               )}
                 <Typography variant="caption" color="textSecondary">
                  Note: Changes are applied when 'Start' is clicked.
                 </Typography>
            </Paper>
          </Grid>

          {/* Status Display */}
          <Grid item xs={12} md={7}>
             <Paper sx={{ p: 2, height: '100%' }}>
              <Typography variant="h6" gutterBottom>Status</Typography>
              {loading && !status && <CircularProgress size={24} />}
              {!status && !loading && <Typography>No status data available. Try fetching.</Typography>}
              {status && (
                <Grid container spacing={1}>
                  <Grid item xs={12}>
                     <Card variant="outlined">
                       <CardContent sx={{ textAlign: 'center', bgcolor: status.is_generating ? 'success.light' : 'warning.light' }}>
                           <Typography variant="h5" component="div">
                            {status.is_generating ? 'GENERATING' : 'STOPPED'}
                           </Typography>
                       </CardContent>
                     </Card>
                  </Grid>
                  <Grid item xs={6}>
                      <Typography variant="body1">Messages/sec:</Typography>
                  </Grid>
                  <Grid item xs={6}>
                       <Typography variant="h6" align='right'>{lastMessagesPerSecond}</Typography>
                  </Grid>
                  <Grid item xs={6}>
                    <Typography>Total Generated:</Typography>
                  </Grid>
                  <Grid item xs={6} sx={{ textAlign: 'right' }}>
                    <Typography>{status.total_generated ?? 'N/A'}</Typography>
                  </Grid>
                   <Grid item xs={6}>
                     <Typography>Total Duplicates:</Typography>
                  </Grid>
                  <Grid item xs={6} sx={{ textAlign: 'right' }}>
                    <Typography>{status.total_duplicates ?? 'N/A'} ({status.config?.duplicate_percent}%)</Typography>
                  </Grid>
                  <Grid item xs={6}>
                    <Typography>Mode:</Typography>
                  </Grid>
                  <Grid item xs={6} sx={{ textAlign: 'right' }}>
                    <Typography>{status.config?.use_batch ? `Batch (Size: ${status.config.batch_size})` : 'Individual'}</Typography>
                  </Grid>
                   <Grid item xs={6}>
                    <Typography>Interval:</Typography>
                  </Grid>
                  <Grid item xs={6} sx={{ textAlign: 'right' }}>
                    <Typography>{status.config?.interval}s</Typography>
                  </Grid>
                  <Grid item xs={6}>
                    <Typography>Stations:</Typography>
                  </Grid>
                  <Grid item xs={6} sx={{ textAlign: 'right' }}>
                    <Typography>{status.config?.stations}</Typography>
                  </Grid>
                   <Grid item xs={12} sx={{ mt: 1}}>
                    <Typography variant='caption' color='textSecondary'>Collector: {status.info?.external_collector_url ?? 'N/A'}</Typography>
                  </Grid>
                </Grid>
              )}
            </Paper>
          </Grid>
        </Grid>
      </Box>
    </Container>
  );
};

export default GeneratorUI; 