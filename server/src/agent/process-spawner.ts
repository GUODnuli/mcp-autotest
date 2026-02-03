import { spawn, type ChildProcess } from 'child_process';
import path from 'path';
import fs from 'fs';
import { getConfig } from '../config/index.js';
import { getLogger } from '../config/logger.js';
import type { SpawnAgentParams } from './types.js';

const LOGS_DIR = path.resolve('logs');

function ensureLogsDir(): void {
  if (!fs.existsSync(LOGS_DIR)) {
    fs.mkdirSync(LOGS_DIR, { recursive: true });
  }
}

export function spawnAgentProcess(params: SpawnAgentParams): ChildProcess {
  const config = getConfig();
  const logger = getLogger();
  ensureLogsDir();

  const agentScript = path.resolve(config.agent.scriptPath);
  const pythonPath = config.agent.pythonPath;

  const args = [
    agentScript,
    '--query-from-stdin',
    '--studio_url', params.studioUrl,
    '--conversation_id', params.conversationId,
    '--reply_id', params.replyId,
    '--llmProvider', params.llmProvider,
    '--modelName', params.modelName,
    '--apiKey', params.apiKey,
    '--writePermission', String(params.writePermission ?? false),
    '--workspace', params.workspace ?? path.resolve('.'),
  ];

  if (params.clientKwargs) {
    args.push('--clientKwargs', JSON.stringify(params.clientKwargs));
  }
  if (params.generateKwargs) {
    args.push('--generateKwargs', JSON.stringify(params.generateKwargs));
  }

  logger.info(
    { conversationId: params.conversationId, replyId: params.replyId },
    'Spawning agent process'
  );

  const env = {
    ...process.env,
    PYTHONIOENCODING: 'utf-8',
    PYTHONUTF8: '1',
    NO_PROXY: 'localhost,127.0.0.1,dashscope.aliyuncs.com,aliyuncs.com',
    no_proxy: 'localhost,127.0.0.1,dashscope.aliyuncs.com,aliyuncs.com',
  };

  const child = spawn(pythonPath, args, {
    stdio: ['pipe', 'pipe', 'pipe'],
    env,
    cwd: path.resolve('.'),
  });

  // Log file for this agent
  const logFile = path.join(LOGS_DIR, `agent_${params.conversationId}.log`);
  const logStream = fs.createWriteStream(logFile, { flags: 'a' });

  const separator = `\n${'='.repeat(60)}\n[${new Date().toISOString()}] Agent started | reply_id: ${params.replyId}\n${'='.repeat(60)}\n`;
  logStream.write(separator);

  // Capture stdout
  if (child.stdout) {
    child.stdout.on('data', (data: Buffer) => {
      const text = data.toString('utf-8');
      logStream.write(`[stdout] ${text}`);
      logger.debug(
        { conversationId: params.conversationId.slice(0, 8) },
        `Agent stdout: ${text.trim()}`
      );
    });
  }

  // Capture stderr
  if (child.stderr) {
    child.stderr.on('data', (data: Buffer) => {
      const text = data.toString('utf-8');
      logStream.write(`[stderr] ${text}`);
      logger.warn(
        { conversationId: params.conversationId.slice(0, 8) },
        `Agent stderr: ${text.trim()}`
      );
    });
  }

  // Write query to stdin
  if (child.stdin) {
    try {
      child.stdin.write(params.query + '\n');
      child.stdin.end();
      logger.info({ replyId: params.replyId }, 'Query written to agent stdin');
    } catch (err) {
      logger.error({ err, replyId: params.replyId }, 'Failed to write query to stdin');
    }
  }

  // Handle process exit
  child.on('exit', (code, signal) => {
    logStream.write(`\n[EXIT] code=${code} signal=${signal}\n`);
    logStream.end();
    logger.info(
      { conversationId: params.conversationId, code, signal },
      'Agent process exited'
    );
  });

  child.on('error', (err) => {
    logStream.write(`\n[ERROR] ${err.message}\n`);
    logStream.end();
    logger.error(
      { err, conversationId: params.conversationId },
      'Agent process error'
    );
  });

  return child;
}
