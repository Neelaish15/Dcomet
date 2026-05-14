
import React, { useEffect, useState, useRef } from 'react';
import axios from 'axios';
import { Container, Typography, Button, Box, Paper, CircularProgress, List, ListItem, ListItemText, Divider, AppBar, Toolbar } from '@mui/material';

const API_BASE = 'http://localhost:8000';

function App() {
  const [status, setStatus] = useState({ running: false, cycles: 0 });
  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(false);
  const intervalRef = useRef(null);

  // Poll simulation status and data
  useEffect(() => {
    if (status.running) {
      intervalRef.current = setInterval(() => {
        fetchStatus();
        fetchData();
      }, 1000);
    } else {
      clearInterval(intervalRef.current);
    }
    return () => clearInterval(intervalRef.current);
    // eslint-disable-next-line
  }, [status.running]);

  const fetchStatus = async () => {
    try {
      const res = await axios.get(`${API_BASE}/simulation_status`);
      setStatus(res.data);
    } catch (e) {
      setStatus({ running: false, cycles: 0 });
    }
  };

  const fetchData = async () => {
    try {
      const res = await axios.get(`${API_BASE}/simulation_data`);
      setData(res.data);
    } catch (e) {
      setData([]);
    }
  };

  const startSimulation = async () => {
    setLoading(true);
    await axios.post(`${API_BASE}/start_simulation`, { num_cycles: 10 });
    setLoading(false);
    fetchStatus();
    fetchData();
  };

  const stopSimulation = async () => {
    setLoading(true);
    await axios.post(`${API_BASE}/stop_simulation`);
    setLoading(false);
    fetchStatus();
  };

  useEffect(() => {
    fetchStatus();
    fetchData();
    // eslint-disable-next-line
  }, []);

  return (
    <Container maxWidth="md" sx={{ mt: 4 }}>
      <AppBar position="static" color="primary">
        <Toolbar>
          <Typography variant="h6" sx={{ flexGrow: 1 }}>
            DCOMET Dashboard
          </Typography>
        </Toolbar>
      </AppBar>
      <Box sx={{ my: 4 }}>
        <Paper sx={{ p: 3, mb: 2 }}>
          <Typography variant="h5" gutterBottom>
            Simulation Status
          </Typography>
          <Typography>Status: {status.running ? 'Running' : 'Stopped'}</Typography>
          <Typography>Cycles Completed: {status.cycles}</Typography>
          <Box sx={{ mt: 2 }}>
            <Button variant="contained" color="success" onClick={startSimulation} disabled={status.running || loading} sx={{ mr: 2 }}>
              Start Simulation
            </Button>
            <Button variant="contained" color="error" onClick={stopSimulation} disabled={!status.running || loading}>
              Stop Simulation
            </Button>
            {loading && <CircularProgress size={24} sx={{ ml: 2 }} />}
          </Box>
        </Paper>
        <Paper sx={{ p: 3 }}>
          <Typography variant="h5" gutterBottom>
            Trading Cycles
          </Typography>
          {data.length === 0 && <Typography>No data yet.</Typography>}
          <List>
            {data.map((cycle, idx) => (
              <React.Fragment key={idx}>
                <ListItem alignItems="flex-start">
                  <ListItemText
                    primary={`Cycle #${cycle.cycle}`}
                    secondary={
                      <>
                        {cycle.trades && cycle.trades.length > 0 ? (
                          <>
                            {cycle.trades.map((trade, tIdx) => (
                              <div key={tIdx}>
                                <b>Trade:</b> {JSON.stringify(trade)}
                              </div>
                            ))}
                          </>
                        ) : (
                          <span>No trades</span>
                        )}
                      </>
                    }
                  />
                </ListItem>
                <Divider />
              </React.Fragment>
            ))}
          </List>
        </Paper>
      </Box>
    </Container>
  );
}

export default App;
