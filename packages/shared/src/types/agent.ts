/**
 * Shared agent types.
 *
 * These types mirror the backend's `agents` table model. Extend as new
 * columns are added in later phases.
 */

export interface Agent {
  id: string; // UUID
  name: string;
  description: string | null;
  created_at: string; // ISO 8601 datetime
  updated_at: string; // ISO 8601 datetime
}

export interface AgentCreate {
  name: string;
  description?: string;
}

export interface AgentUpdate {
  name?: string;
  description?: string;
}
