import { v4 as uuidv4 } from 'uuid';
import { getLogger } from '../../config/logger.js';
import { getConfig } from '../../config/index.js';
import { getAgentManager } from '../../agent/agent-manager.js';
import { getSocketManager } from '../../socket/socket-manager.js';
import {
  createConversationInternal,
  createMessageInternal,
  createMessageWithMetadataInternal,
  updateConversationTitleInternal,
} from '../conversation/conversation.service.js';
import { generateTitle } from '../../llm/title-generator.js';
import type { AgentMessageData } from '../../agent/types.js';

export async function sendMessage(
  message: string,
  userId: string,
  conversationId?: string | null
) {
  const logger = getLogger();
  const agentManager = getAgentManager();

  // Create conversation if needed
  if (!conversationId) {
    const conv = await createConversationInternal(userId, message.slice(0, 50));
    conversationId = conv.id;
  }

  // Create reply ID
  const replyId = uuidv4();

  // Save user message
  const userMessageId = uuidv4();
  await createMessageInternal(conversationId, 'user', message, userMessageId);

  // Broadcast replying state via Socket.IO
  try {
    const socketManager = getSocketManager();
    await socketManager.broadcastReplyingState({
      replying: true,
      conversation_id: conversationId,
    });
  } catch {
    // Socket not ready
  }

  // Get model config from TOML (simplified - use env or defaults)
  const config = getConfig();
  const studioUrl = `http://localhost:${config.port}`;

  // Build query JSON
  const query = JSON.stringify([{ type: 'text', text: message }]);

  // Spawn agent with write permission
  await agentManager.spawnAgent({
    conversationId,
    replyId,
    userId,
    query,
    studioUrl,
    llmProvider: config.llm.provider,
    modelName: config.llm.modelName,
    apiKey: config.llm.apiKey,
    writePermission: true,
    workspace: config.storage.root,
  });

  return {
    conversation_id: conversationId,
    reply_id: replyId,
    status: 'processing',
    timestamp: new Date().toISOString(),
  };
}

export interface SSEStreamOptions {
  message: string;
  userId: string;
  conversationId?: string | null;
  uploadedFiles?: string[];
}

export async function* sendMessageStreaming(
  options: SSEStreamOptions
): AsyncGenerator<Record<string, unknown>> {
  const { message, userId, uploadedFiles } = options;
  let { conversationId } = options;
  const logger = getLogger();
  const agentManager = getAgentManager();
  const config = getConfig();

  // Create conversation if needed
  let isNewConversation = false;
  if (!conversationId) {
    const conv = await createConversationInternal(userId, message.slice(0, 50));
    conversationId = conv.id;
    isNewConversation = true;
  }

  const replyId = uuidv4();
  const userMessageId = uuidv4();
  const assistantMessageId = uuidv4();

  // Collect assistant message content and events for persistence
  const assistantContent: string[] = [];
  const assistantEvents: Array<Record<string, unknown>> = [];

  // Save user message
  await createMessageInternal(conversationId, 'user', message, userMessageId);

  // Broadcast replying state
  try {
    const socketManager = getSocketManager();
    await socketManager.broadcastReplyingState({
      replying: true,
      conversation_id: conversationId,
    });
  } catch {
    // Socket not ready
  }

  // Yield start event
  yield {
    type: 'start',
    conversation_id: conversationId,
    reply_id: replyId,
  };

  // Build query JSON with context
  const queryBlocks: Array<{ type: string; text: string }> = [];

  // File storage path for this conversation
  const fileStoragePath = `chat/${userId}/${conversationId}`;

  if (uploadedFiles && uploadedFiles.length > 0) {
    const filesWithPaths = uploadedFiles.map(f => `${fileStoragePath}/${f}`);
    queryBlocks.push({
      type: 'text',
      text: `[SYSTEM CONTEXT]
user_id: ${userId}
conversation_id: ${conversationId}
file_storage_path: ${fileStoragePath}
uploaded_files:
${filesWithPaths.map(f => `  - ${f}`).join('\n')}

IMPORTANT: To read uploaded files, use:
  - read_file("${fileStoragePath}/filename")
  - glob_files("*", "${fileStoragePath}")
[/SYSTEM CONTEXT]`,
    });
  } else {
    queryBlocks.push({
      type: 'text',
      text: `[SYSTEM CONTEXT]
user_id: ${userId}
conversation_id: ${conversationId}
file_storage_path: ${fileStoragePath}
uploaded_files: (none)
[/SYSTEM CONTEXT]`,
    });
  }
  queryBlocks.push({ type: 'text', text: message });

  const query = JSON.stringify(queryBlocks);
  const studioUrl = `http://localhost:${config.port}`;

  // Spawn agent with write permission and workspace
  await agentManager.spawnAgent({
    conversationId,
    replyId,
    userId,
    query,
    studioUrl,
    llmProvider: config.llm.provider,
    modelName: config.llm.modelName,
    apiKey: config.llm.apiKey,
    writePermission: true,
    workspace: config.storage.root,
  });

  // Consume messages from agent manager via callback
  const messageQueue: Array<AgentMessageData | null> = [];
  let resolveWaiting: (() => void) | null = null;

  agentManager.registerSSECallback(replyId, (msg) => {
    messageQueue.push(msg);
    if (resolveWaiting) {
      resolveWaiting();
      resolveWaiting = null;
    }
  });

  // Async title generation for new conversations (non-blocking).
  // Must be AFTER registerSSECallback so pushToSSEQueue finds the callback.
  if (isNewConversation) {
    generateAndUpdateTitle(conversationId, userId, message, replyId, agentManager);
  }

  try {
    while (true) {
      // Wait for message or timeout
      if (messageQueue.length === 0) {
        const timeoutPromise = new Promise<void>((resolve) => {
          const timer = setTimeout(resolve, 30000);
          resolveWaiting = () => {
            clearTimeout(timer);
            resolve();
          };
        });
        await timeoutPromise;
      }

      // Process all available messages
      while (messageQueue.length > 0) {
        const msg = messageQueue.shift()!;

        if (msg === null) {
          // End signal — save assistant message and yield done
          await saveAssistantMessage(
            conversationId!,
            assistantMessageId,
            assistantContent.join(''),
            assistantEvents,
            logger
          );
          yield {
            type: 'done',
            conversation_id: conversationId,
            timestamp: new Date().toISOString(),
          };
          return;
        }

        // Collect content and events for persistence
        const msgRecord = msg as Record<string, unknown>;
        if (msgRecord.type === 'chunk' || msgRecord.type === 'text') {
          const content = (msgRecord.content as string) || '';
          assistantContent.push(content);
          assistantEvents.push({ type: 'text', content });
        } else if (msgRecord.type === 'thinking') {
          assistantEvents.push({ type: 'thinking', content: msgRecord.content });
        } else if (msgRecord.type === 'tool_call') {
          assistantEvents.push({
            type: 'tool_call',
            id: msgRecord.id,
            name: msgRecord.name,
            input: msgRecord.input,
          });
        } else if (msgRecord.type === 'tool_result') {
          assistantEvents.push({
            type: 'tool_result',
            id: msgRecord.id,
            name: msgRecord.name,
            output: msgRecord.output,
            success: msgRecord.success,
          });
        }

        yield msg as unknown as Record<string, unknown>;
      }

      // If no messages came (timeout), check if agent still running
      if (messageQueue.length === 0 && !agentManager.isRunning(replyId)) {
        break;
      }

      // Send heartbeat on timeout
      if (messageQueue.length === 0) {
        yield { type: 'heartbeat' };
      }
    }

    // Agent stopped without sending end signal — save message and yield done
    await saveAssistantMessage(
      conversationId!,
      assistantMessageId,
      assistantContent.join(''),
      assistantEvents,
      logger
    );
    yield {
      type: 'done',
      conversation_id: conversationId,
      timestamp: new Date().toISOString(),
    };
  } finally {
    agentManager.removeSSECallbacks(replyId);

    // Broadcast replying state off
    try {
      const socketManager = getSocketManager();
      await socketManager.broadcastReplyingState({
        replying: false,
        conversation_id: null,
      });
    } catch {
      // Socket not ready
    }
  }
}

/**
 * Asynchronously generate a creative title for a new conversation
 * and push it to the SSE stream. Fire-and-forget — errors are logged
 * but never propagated.
 */
async function generateAndUpdateTitle(
  conversationId: string,
  userId: string,
  message: string,
  replyId: string,
  agentManager: ReturnType<typeof getAgentManager>
): Promise<void> {
  const logger = getLogger();
  try {
    const title = await generateTitle(message);
    await updateConversationTitleInternal(conversationId, userId, title);
    agentManager.pushToSSEQueue(replyId, {
      type: 'title_generated',
      conversation_id: conversationId,
      title,
    } as unknown as AgentMessageData);
    logger.info({ conversationId, title }, 'Title generated for new conversation');
  } catch (err) {
    logger.error({ err, conversationId }, 'Failed to generate title');
  }
}

/**
 * Save assistant message with events to database
 */
async function saveAssistantMessage(
  conversationId: string,
  messageId: string,
  content: string,
  events: Array<Record<string, unknown>>,
  logger: ReturnType<typeof getLogger>
): Promise<void> {
  try {
    // Merge adjacent text events for cleaner storage
    const mergedEvents = mergeAdjacentTextEvents(events);

    await createMessageWithMetadataInternal(
      conversationId,
      'assistant',
      content || '(no text content)',
      messageId,
      { events: mergedEvents }
    );
    logger.debug({ conversationId, messageId, eventCount: mergedEvents.length }, 'Saved assistant message');
  } catch (err) {
    logger.error({ err, conversationId, messageId }, 'Failed to save assistant message');
  }
}

/**
 * Merge adjacent text events to reduce storage size
 */
function mergeAdjacentTextEvents(events: Array<Record<string, unknown>>): Array<Record<string, unknown>> {
  const result: Array<Record<string, unknown>> = [];
  for (const event of events) {
    const last = result[result.length - 1];
    if (event.type === 'text' && last?.type === 'text') {
      last.content = (last.content as string) + (event.content as string);
    } else {
      result.push({ ...event });
    }
  }
  return result;
}

export async function interruptAgent(replyId: string): Promise<boolean> {
  const agentManager = getAgentManager();
  const success = await agentManager.terminateAgent(replyId);

  if (success) {
    // Broadcast cancelled via Socket.IO
    try {
      const socketManager = getSocketManager();
      await socketManager.broadcastReplyingState({
        replying: false,
        conversation_id: null,
      });
      await socketManager.broadcastCancelled(replyId);
    } catch {
      // Socket not ready
    }
  }

  return success;
}
