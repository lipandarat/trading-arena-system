import React from 'react';
import {
  Typography,
  Grid,
  Card,
  CardContent,
  Box,
} from '@mui/material';

export const Dashboard: React.FC = () => {
  return (
    <Box>
      <Typography variant="h4" component="h1" gutterBottom>
        Trading Dashboard
      </Typography>

      <Grid container spacing={3}>
        <Grid item xs={12} md={3}>
          <Card>
            <CardContent>
              <Typography variant="h6">Active Agents</Typography>
              <Typography variant="h4">3</Typography>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} md={3}>
          <Card>
            <CardContent>
              <Typography variant="h6">Total Return</Typography>
              <Typography variant="h4">+12.4%</Typography>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} md={3}>
          <Card>
            <CardContent>
              <Typography variant="h6">Win Rate</Typography>
              <Typography variant="h4">64%</Typography>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} md={3}>
          <Card>
            <CardContent>
              <Typography variant="h6">Sharpe Ratio</Typography>
              <Typography variant="h4">1.85</Typography>
            </CardContent>
          </Card>
        </Grid>
      </Grid>
    </Box>
  );
};