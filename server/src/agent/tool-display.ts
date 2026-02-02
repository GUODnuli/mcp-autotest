/**
 * 工具前端展示配置
 *
 * 数据驱动：优先从 .testagent/settings.json 读取 toolDisplay 配置，
 * 读取失败时回退到硬编码默认值。
 *
 * 日志中仍保留原始英文名称，仅 SSE 推送给前端时做转换/过滤。
 */

import { readFileSync } from 'fs';
import { dirname, resolve } from 'path';
import { fileURLToPath } from 'url';

const __dirname = dirname(fileURLToPath(import.meta.url));

/** 硬编码默认显示名 */
const DEFAULT_DISPLAY_NAMES: Record<string, string> = {
  // ===== 框架内置工具 =====
  reset_equipped_tools: '重置工具组',
  equip_tool_group: '激活工具组',

  // ===== 基础文件工具 =====
  list_uploaded_files: '列出上传文件',
  safe_view_text_file: '查看文件内容',
  safe_write_text_file: '写入文件内容',

  // ===== 文档解析工具 =====
  read_document: '读取文档',
  extract_api_spec: '提取接口规范',
  validate_api_spec: '校验接口规范',

  // ===== 用例生成工具 =====
  generate_positive_cases: '生成正向用例',
  generate_negative_cases: '生成反向用例',
  generate_security_cases: '生成安全用例',
  apply_business_rules: '应用业务规则',

  // ===== 测试执行工具 =====
  execute_api_test: '执行接口测试',
  validate_response: '校验响应结果',
  capture_metrics: '采集性能指标',

  // ===== 报告生成工具 =====
  generate_test_report: '生成测试报告',
  diagnose_failures: '诊断失败原因',
  suggest_improvements: '生成改进建议',
};

/** 硬编码默认隐藏工具 */
const DEFAULT_HIDDEN_TOOLS: readonly string[] = [
  'reset_equipped_tools',
  'equip_tool_group',
];

interface ToolDisplayConfig {
  names: Record<string, string>;
  hidden: ReadonlySet<string>;
}

function loadToolDisplayConfig(): ToolDisplayConfig {
  const settingsPath = resolve(__dirname, '..', '..', '..', '.testagent', 'settings.json');

  try {
    const raw = readFileSync(settingsPath, 'utf-8');
    const settings = JSON.parse(raw);
    const toolDisplay = settings?.toolDisplay;

    if (!toolDisplay) {
      return {
        names: { ...DEFAULT_DISPLAY_NAMES },
        hidden: new Set(DEFAULT_HIDDEN_TOOLS),
      };
    }

    const names: Record<string, string> = {
      ...DEFAULT_DISPLAY_NAMES,
      ...(toolDisplay.names ?? {}),
    };

    const hiddenList: string[] = Array.isArray(toolDisplay.hidden)
      ? toolDisplay.hidden
      : [...DEFAULT_HIDDEN_TOOLS];

    return { names, hidden: new Set(hiddenList) };
  } catch {
    return {
      names: { ...DEFAULT_DISPLAY_NAMES },
      hidden: new Set(DEFAULT_HIDDEN_TOOLS),
    };
  }
}

let config = loadToolDisplayConfig();

/** 导出显示名映射（兼容旧代码引用） */
export const toolDisplayNames: Record<string, string> = config.names;

/** 导出隐藏工具集合（兼容旧代码引用） */
export const hiddenTools: ReadonlySet<string> = config.hidden;

/**
 * 获取工具的前端显示名称。
 * 若未在映射表中定义，则原样返回。
 */
export function getToolDisplayName(name: string): string {
  return config.names[name] ?? name;
}

/**
 * 判断工具是否应对前端隐藏。
 */
export function isToolHidden(name: string): boolean {
  return config.hidden.has(name);
}

/**
 * 重新加载 toolDisplay 配置（支持热更新场景）。
 */
export function reloadToolDisplayConfig(): void {
  config = loadToolDisplayConfig();
  // 更新导出引用
  Object.keys(toolDisplayNames).forEach((k) => delete toolDisplayNames[k]);
  Object.assign(toolDisplayNames, config.names);
}
