import axios, { AxiosResponse } from 'axios';
import { User, Agent, Position, Order, PerformanceMetrics } from '@/types';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://arena-api:8000';

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Add auth token to requests
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Handle 401 responses
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('access_token');
      window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);

export const authApi = {
  login: async (username: string, password: string) => {
    const response: AxiosResponse<{ access_token: string; token_type: string; expires_in: number }> =
      await api.post('/api/v1/auth/login', { username, password });
    return response.data;
  },

  getProfile: async (): Promise<User> => {
    const response: AxiosResponse<User> = await api.get('/api/v1/auth/profile');
    return response.data;
  },
};

export const tradingApi = {
  getAgents: async (skip = 0, limit = 100): Promise<Agent[]> => {
    const response: AxiosResponse<Agent[]> = await api.get(`/api/v1/trading/agents?skip=${skip}&limit=${limit}`);
    return response.data;
  },

  createAgent: async (agentData: Partial<Agent>): Promise<Agent> => {
    const response: AxiosResponse<Agent> = await api.post('/api/v1/trading/agents', agentData);
    return response.data;
  },

  getPositions: async (): Promise<Position[]> => {
    const response: AxiosResponse<Position[]> = await api.get('/api/v1/trading/positions');
    return response.data;
  },

  getPerformance: async (): Promise<PerformanceMetrics> => {
    const response: AxiosResponse<PerformanceMetrics> = await api.get('/api/v1/trading/performance');
    return response.data;
  },
};