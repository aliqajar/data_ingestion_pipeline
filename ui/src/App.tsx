import React from 'react';
import { BrowserRouter as Router, Routes, Route, Link } from 'react-router-dom';
import { AppBar, Toolbar, Typography, Button, Container, Box } from '@mui/material';
import QueryUI from './components/QueryUI';
import GeneratorUI from './components/GeneratorUI';
import './App.css';

function App() {
  return (
    <Router>
      <Box sx={{ display: 'flex', flexDirection: 'column', minHeight: '100vh' }}>
        <AppBar position="static">
          <Toolbar>
            <Typography variant="h6" component="div" sx={{ flexGrow: 1 }}>
              Weather Data System
            </Typography>
            {/* Link to Generator UI */}
            <Button color="inherit" component={Link} to="/">
              Generator
            </Button>
            {/* Link to Query UI */}
            <Button color="inherit" component={Link} to="/query">
              Query Interface
            </Button>
          </Toolbar>
        </AppBar>

        <Container component="main" sx={{ flexGrow: 1, py: 3 }}>
          <Routes>
            {/* Route for the Generator UI */}
            <Route path="/" element={<GeneratorUI />} />

            {/* Route for the Query UI */}
            <Route path="/query" element={<QueryUI />} />
          </Routes>
        </Container>

        <Box component="footer" sx={{ py: 2, px: 2, mt: 'auto', backgroundColor: (theme) =>
            theme.palette.mode === 'light' ? theme.palette.grey[200] : theme.palette.grey[800]
          }}>
          <Container maxWidth="sm">
            <Typography variant="body2" color="text.secondary" align="center">
              {'Copyright © Weather System '}{new Date().getFullYear()}{'.'}
            </Typography>
          </Container>
        </Box>
      </Box>
    </Router>
  );
}

export default App;
