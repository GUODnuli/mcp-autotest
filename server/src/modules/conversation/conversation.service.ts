import { Prisma } from '@prisma/client';
import { getPrisma } from '../../config/database.js';
import { getRedis } from '../../config/redis.js';
import { getLogger } from '../../config/logger.js';
import { NotFoundError, ForbiddenError } from '../../common/errors.js';
import { formatConversation, formatMessage } from '../../common/utils.js';
import { CacheKeys, CacheTTL } from '../../cache/cache-keys.js';
import * as planService from '../plan/plan.service.js';

const CACHE_CONVERSATIONS_TTL = CacheTTL.conversations;
const CACHE_MESSAGES_TTL = CacheTTL.messages;

function conversationsCacheKey(userId: string): string {
  return CacheKeys.conversations(userId);
}

function messagesCacheKey(conversationId: string): string {
  return CacheKeys.messages(conversationId);
}

async function invalidateConversationsCache(userId: string): Promise<void> {
  const redis = getRedis();
  await redis.del(conversationsCacheKey(userId));
}

async function invalidateMessagesCache(conversationId: string): Promise<void> {
  const redis = getRedis();
  await redis.del(messagesCacheKey(conversationId));
}

export async function createConversation(userId: string, title: string) {
  const prisma = getPrisma();
  const logger = getLogger();

  const conversation = await prisma.conversation.create({
    data: { userId, title },
    include: { _count: { select: { messages: true } } },
  });

  await invalidateConversationsCache(userId);
  logger.info({ conversationId: conversation.id, userId }, 'Conversation created');

  return formatConversation(conversation);
}

export async function listConversations(userId: string, limit: number = 100, offset: number = 0) {
  const prisma = getPrisma();
  const redis = getRedis();

  // Try cache first
  const cacheKey = conversationsCacheKey(userId);
  const cacheTag = `${limit}:${offset}`;
  try {
    const cached = await redis.hget(cacheKey, cacheTag);
    if (cached) {
      return JSON.parse(cached);
    }
  } catch {
    // Cache miss, continue
  }

  const conversations = await prisma.conversation.findMany({
    where: { userId },
    orderBy: { updatedAt: 'desc' },
    take: limit,
    skip: offset,
    include: { _count: { select: { messages: true } } },
  });

  const result = conversations.map(formatConversation);

  // Cache result
  try {
    await redis.hset(cacheKey, cacheTag, JSON.stringify(result));
    await redis.expire(cacheKey, CACHE_CONVERSATIONS_TTL);
  } catch {
    // Cache write failure is non-critical
  }

  return result;
}

export async function getConversation(conversationId: string, userId: string) {
  const prisma = getPrisma();

  const conversation = await prisma.conversation.findUnique({
    where: { id: conversationId },
    include: { _count: { select: { messages: true } } },
  });

  if (!conversation) {
    throw new NotFoundError('对话');
  }

  if (conversation.userId !== userId) {
    throw new ForbiddenError('无权访问此对话');
  }

  return formatConversation(conversation);
}

export async function updateConversation(conversationId: string, userId: string, title: string) {
  const prisma = getPrisma();

  const conversation = await prisma.conversation.findUnique({
    where: { id: conversationId },
  });

  if (!conversation) {
    throw new NotFoundError('对话');
  }
  if (conversation.userId !== userId) {
    throw new ForbiddenError('无权修改此对话');
  }

  await prisma.conversation.update({
    where: { id: conversationId },
    data: { title },
  });

  await invalidateConversationsCache(userId);

  return { message: '对话标题已更新' };
}

export async function deleteConversation(conversationId: string, userId: string) {
  const prisma = getPrisma();

  const conversation = await prisma.conversation.findUnique({
    where: { id: conversationId },
  });

  if (!conversation) {
    throw new NotFoundError('对话');
  }
  if (conversation.userId !== userId) {
    throw new ForbiddenError('无权删除此对话');
  }

  await prisma.conversation.delete({ where: { id: conversationId } });

  await invalidateConversationsCache(userId);
  await invalidateMessagesCache(conversationId);

  return { message: '对话已删除' };
}

// Message operations

export async function createMessage(
  conversationId: string,
  userId: string,
  role: string,
  content: string
) {
  const prisma = getPrisma();

  const conversation = await prisma.conversation.findUnique({
    where: { id: conversationId },
  });

  if (!conversation) {
    throw new NotFoundError('对话');
  }
  if (conversation.userId !== userId) {
    throw new ForbiddenError('无权在此对话中发送消息');
  }

  const message = await prisma.message.create({
    data: { conversationId, role, content },
  });

  // Touch conversation updatedAt
  await prisma.conversation.update({
    where: { id: conversationId },
    data: { updatedAt: new Date() },
  });

  await invalidateMessagesCache(conversationId);
  await invalidateConversationsCache(userId);

  return formatMessage(message);
}

export async function listMessages(
  conversationId: string,
  userId: string,
  limit: number = 100,
  offset: number = 0
) {
  const prisma = getPrisma();
  const redis = getRedis();

  // Verify access
  const conversation = await prisma.conversation.findUnique({
    where: { id: conversationId },
  });

  if (!conversation) {
    throw new NotFoundError('对话');
  }
  if (conversation.userId !== userId) {
    throw new ForbiddenError('无权访问此对话的消息');
  }

  // Try cache
  const cacheKey = messagesCacheKey(conversationId);
  const cacheTag = `${limit}:${offset}`;
  try {
    const cached = await redis.hget(cacheKey, cacheTag);
    if (cached) {
      return JSON.parse(cached);
    }
  } catch {
    // Cache miss
  }

  const messages = await prisma.message.findMany({
    where: { conversationId },
    orderBy: { createdAt: 'asc' },
    take: limit,
    skip: offset,
  });

  const result = messages.map(formatMessage);

  // Cache
  try {
    await redis.hset(cacheKey, cacheTag, JSON.stringify(result));
    await redis.expire(cacheKey, CACHE_MESSAGES_TTL);
  } catch {
    // Non-critical
  }

  return result;
}

/**
 * Internal: create message without auth check (used by chat service)
 */
export async function createMessageInternal(
  conversationId: string,
  role: string,
  content: string,
  messageId?: string
) {
  const prisma = getPrisma();

  const message = await prisma.message.create({
    data: {
      ...(messageId ? { id: messageId } : {}),
      conversationId,
      role,
      content,
    },
  });

  await prisma.conversation.update({
    where: { id: conversationId },
    data: { updatedAt: new Date() },
  });

  await invalidateMessagesCache(conversationId);

  return message;
}

/**
 * Internal: create message with metadata (used by chat service for assistant messages)
 */
export async function createMessageWithMetadataInternal(
  conversationId: string,
  role: string,
  content: string,
  messageId: string,
  metadata: Record<string, unknown>
) {
  const prisma = getPrisma();

  const message = await prisma.message.create({
    data: {
      id: messageId,
      conversationId,
      role,
      content,
      metadata: metadata as Prisma.InputJsonValue,
    },
  });

  await prisma.conversation.update({
    where: { id: conversationId },
    data: { updatedAt: new Date() },
  });

  await invalidateMessagesCache(conversationId);

  return message;
}

/**
 * Internal: update conversation title without auth check (used by title generator)
 */
export async function updateConversationTitleInternal(
  conversationId: string,
  userId: string,
  title: string
): Promise<void> {
  const prisma = getPrisma();

  await prisma.conversation.update({
    where: { id: conversationId },
    data: { title },
  });

  await invalidateConversationsCache(userId);
}

/**
 * Internal: create conversation without formatted response
 */
export async function createConversationInternal(userId: string, title: string) {
  const prisma = getPrisma();

  const conversation = await prisma.conversation.create({
    data: { userId, title },
  });

  await invalidateConversationsCache(userId);

  return conversation;
}

/**
 * Get the coordinator plan for a conversation
 */
export async function getConversationPlan(conversationId: string, userId: string) {
  const prisma = getPrisma();

  // Verify access
  const conversation = await prisma.conversation.findUnique({
    where: { id: conversationId },
  });

  if (!conversation) {
    throw new NotFoundError('对话');
  }
  if (conversation.userId !== userId) {
    throw new ForbiddenError('无权访问此对话的计划');
  }

  return planService.getPlan(conversationId);
}
