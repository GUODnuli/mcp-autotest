# Prompts 目录说明

本目录包含所有 LLM 调用所需的 Prompt 模板和 JSON Schema 定义。

## 文件结构

### Prompt 模板 (.txt)
- word_to_interfaces.txt - Word 文档转接口规范的 System Prompt
- generate_testcases.txt - 测试用例生成的 System Prompt

### JSON Schema (.json)
- interface_schema.json - API 接口规范的 JSON Schema
- testcase_schema.json - 测试用例的 JSON Schema

## 使用方式

### 1. 在代码中使用 PromptBuilder

```python
from backend.common.prompt_builder import get_prompt_builder

# 获取 PromptBuilder 实例
builder = get_prompt_builder()

# 构建 Word→接口 Prompt
prompts = builder.build_word_to_interfaces_prompt(
    word_content=word_content_dict,
    business_context="贷款利率计算业务"
)
system_prompt = prompts["system_prompt"]
user_query = prompts["user_query"]

# 构建测试用例生成 Prompt
prompts = builder.build_generate_testcases_prompt(
    interface_spec=interface_dict,
    strategies=["positive", "negative", "boundary"],
    count_per_strategy=3
)
```

### 2. 使用统一的 LLMClient

```python
from backend.common.llm_client import get_llm_client

# 初始化（需要 Dify 配置）
llm_client = get_llm_client(dify_config)

# Word 文档转接口
result = llm_client.word_to_interfaces(
    word_content=word_content,
    task_id=task_id
)
interfaces = result["interfaces"]

# 生成测试用例
result = llm_client.generate_testcases(
    interface_spec=interface,
    strategies=["positive", "negative"],
    count_per_strategy=3,
    task_id=task_id
)
testcases = result["testcases"]
```

## 修改 Prompt

直接编辑对应的 .txt 文件即可，修改后会自动生效（热重载）。

## 注意事项

1. **Prompt 模板**使用纯文本格式，可以包含 Markdown 标记
2. **JSON Schema** 必须是合法的 JSON 格式
3. 修改 Schema 后需确保与 LLM 输出格式兼容
4. System Prompt 会自动附加对应的 JSON Schema
