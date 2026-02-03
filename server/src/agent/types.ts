export interface SpawnAgentParams {
  conversationId: string;
  replyId: string;
  userId: string;
  query: string;
  studioUrl: string;
  llmProvider: string;
  modelName: string;
  apiKey: string;
  writePermission?: boolean;
  workspace?: string;
  clientKwargs?: Record<string, unknown>;
  generateKwargs?: Record<string, unknown>;
}

export interface PendingReply {
  conversationId: string;
  replyId: string;
  userId: string;
  messages: AgentMessageData[];
  finished: boolean;
  cancelled?: boolean;
}

export interface AgentMessageData {
  id?: string;
  content: string | Array<{ type: string; text?: string; thinking?: string }>;
  role?: string;
  sequence?: number;
  _accumulated_content?: string;
  [key: string]: unknown;
}

export interface AgentReplyState {
  conversationId: string;
  replyId: string;
  userId: string;
  status: 'starting' | 'running' | 'completed' | 'failed' | 'cancelled';
  startedAt: string;
}

/** Structured event from Python agent hook */
export interface AgentTextEvent {
  type: 'text';
  content: string;
  sequence: number;
}

export interface AgentToolCallEvent {
  type: 'tool_call';
  id: string;
  name: string;
  input: Record<string, unknown> | string;
  sequence: number;
}

export interface AgentToolResultEvent {
  type: 'tool_result';
  id: string;
  name: string;
  output: string;
  success: boolean;
  sequence: number;
}

export type AgentEvent = AgentTextEvent | AgentToolCallEvent | AgentToolResultEvent;

/** Payload format from Python agent hook (new structured format) */
export interface AgentEventsPayload {
  replyId: string;
  events: AgentEvent[];
}

/** Payload format from Python agent hook (legacy format) */
export interface AgentLegacyPayload {
  replyId: string;
  msg: Record<string, unknown>;
}
