export interface User {
  id: number;
  username: string;
  email: string;
  role: 'admin' | 'competitor' | 'trader' | 'spectator';
  is_active: boolean;
}

export interface Agent {
  id: number;
  name: string;
  owner: string;
  llm_model: string;
  status: 'active' | 'paused' | 'stopped' | 'liquidated';
  risk_profile: 'conservative' | 'moderate' | 'aggressive';
  initial_capital: number;
  current_capital: number;
  total_trades: number;
  winning_trades: number;
  win_rate: number;
  total_return: number;
  created_at: string;
  updated_at: string;
}

export interface Position {
  symbol: string;
  side: 'LONG' | 'SHORT';
  size: number;
  entry_price: number;
  mark_price: number;
  unrealized_pnl: number;
  percentage_pnl: number;
}

export interface Order {
  id: string;
  symbol: string;
  side: 'BUY' | 'SELL';
  type: 'MARKET' | 'LIMIT';
  quantity: number;
  price?: number;
  status: string;
  timestamp: string;
  executed_quantity: number;
  executed_price?: number;
}

export interface PerformanceMetrics {
  sharpe_ratio: number;
  sortino_ratio: number;
  max_drawdown: number;
  current_drawdown: number;
  volatility: number;
  total_return: number;
  win_rate: number;
  profit_factor: number;
}

export interface ApiResponse<T> {
  data: T;
  message?: string;
  error?: string;
}