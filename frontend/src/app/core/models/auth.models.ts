/**
 * Authentication and Authorization Models
 * MANTIS AI - Secure trading platform authentication
 */

export interface User {
  id: number;
  username: string;
  email: string;
  role_id: number;
  role_name: string;  // Backend returns role_name, not role
  is_active: boolean;
  last_login: string | null;
  avatar_url?: string | null;  // Avatar URL for user profile pictures
  permissions?: Permission[];
}

export interface Permission {
  resource: string;
  action: string;
}

export interface LoginRequest {
  username: string;
  password: string;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  user: User;
}

export interface RegisterRequest {
  username: string;
  email: string;
  password: string;
  role_name?: string;  // Backend expects role_name ("VIEWER", "TRADER", "ADMIN")
}

export interface RegisterResponse {
  user: User;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
}

export interface AuthState {
  isAuthenticated: boolean;
  currentUser: User | null;
  token: string | null;
}

/**
 * Role IDs mapping
 */
export enum UserRole {
  VIEWER = 1,
  TRADER = 2,
  ADMIN = 3
}

/**
 * Common permissions for authorization checks
 */
export const PERMISSIONS = {
  TRADING: {
    READ: { resource: 'trading', action: 'read' },
    EXECUTE: { resource: 'trading', action: 'execute' },
    WRITE: { resource: 'trading', action: 'write' }
  },
  POSITIONS: {
    READ: { resource: 'positions', action: 'read' },
    WRITE: { resource: 'positions', action: 'write' }
  },
  SETTINGS: {
    READ: { resource: 'settings', action: 'read' },
    WRITE: { resource: 'settings', action: 'write' }
  },
  MODELS: {
    READ: { resource: 'models', action: 'read' },
    TRAIN: { resource: 'models', action: 'train' }
  },
  BACKTEST: {
    READ: { resource: 'backtest', action: 'read' },
    RUN: { resource: 'backtest', action: 'run' }
  }
} as const;
