import { getConfig } from '../config/index.js';
import { getLogger } from '../config/logger.js';

const DASHSCOPE_API_URL = 'https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions';

const SYSTEM_PROMPT =
  '你是一个标题生成器。根据用户的第一条消息，生成一个10字以内的中文短标题，简洁概括用户意图。只输出标题本身，不要加引号、标点或任何额外内容。';

/**
 * Strip `<think>...</think>` blocks that Qwen3 models emit when thinking
 * mode is enabled, leaving only the final answer.
 */
function stripThinkingTags(text: string): string {
  return text.replace(/<think>[\s\S]*?<\/think>/g, '').trim();
}

/**
 * Call DashScope OpenAI-compatible API to generate a short creative title
 * for the given user message.
 *
 * Falls back to `userMessage.slice(0, 10)` on any failure.
 */
export async function generateTitle(userMessage: string): Promise<string> {
  const logger = getLogger();
  const config = getConfig();
  const { apiKey, modelName } = config.llm;

  if (!apiKey) {
    logger.warn('LLM API key not configured, using fallback title');
    return userMessage.slice(0, 10);
  }

  try {
    const response = await fetch(DASHSCOPE_API_URL, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${apiKey}`,
      },
      body: JSON.stringify({
        model: modelName,
        temperature: 1.2,
        max_tokens: 256,
        messages: [
          { role: 'system', content: SYSTEM_PROMPT },
          { role: 'user', content: userMessage.slice(0, 500) },
        ],
        // Disable thinking mode for Qwen3 models to get a clean title
        enable_thinking: false,
      }),
    });

    if (!response.ok) {
      const text = await response.text();
      logger.error({ status: response.status, body: text }, 'Title generation API request failed');
      return userMessage.slice(0, 10);
    }

    const data = (await response.json()) as {
      choices?: Array<{ message?: { content?: string } }>;
    };

    const raw = data.choices?.[0]?.message?.content?.trim() ?? '';
    const title = stripThinkingTags(raw);
    if (!title) {
      logger.warn({ raw: raw.slice(0, 200) }, 'Title generation returned empty content after stripping');
      return userMessage.slice(0, 10);
    }

    return title.slice(0, 20);
  } catch (err) {
    logger.error({ err }, 'Title generation failed');
    return userMessage.slice(0, 10);
  }
}
