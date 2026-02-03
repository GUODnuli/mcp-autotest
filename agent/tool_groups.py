# -*- coding: utf-8 -*-
"""
内置工具组定义

DEPRECATED: Domain tools are now loaded dynamically from skills/*/tools/.
This module is kept for backward compatibility only.

New architecture:
- Base tools: Registered directly in main.py from tool.base package
- Domain tools: Loaded dynamically via _load_skill_tools() in tool_registry.py
- Tool groups: Created automatically per skill with "{skill_name}_tools" naming

This file will be removed in a future version.
"""
from typing import List, Callable


class ToolGroupDefinition:
    """
    工具组定义

    DEPRECATED: Use skill-based tool loading instead.
    """

    def __init__(
        self,
        group_name: str,
        description: str,
        notes: str,
        tools: List[Callable],
    ):
        self.group_name = group_name
        self.description = description
        self.notes = notes
        self.tools = tools


def get_builtin_tool_groups(tool_modules: dict) -> List[ToolGroupDefinition]:
    """
    DEPRECATED: Domain tools are now loaded from skills/*/tools/ directories.

    This function returns legacy tool groups for backward compatibility.
    New code should not use this function.
    """
    """
    获取内置 API 测试工具组定义。

    Args:
        tool_modules: 工具模块字典
            {
                'doc_parser': {...},
                'case_generator': {...},
                'test_executor': {...},
                'report_tools': {...}
            }

    Returns:
        工具组定义列表
    """
    doc_parser = tool_modules.get("doc_parser", {})
    case_generator = tool_modules.get("case_generator", {})
    test_executor = tool_modules.get("test_executor", {})
    report_tools = tool_modules.get("report_tools", {})

    return [
        ToolGroupDefinition(
            group_name="document_parser_tools",
            description="Tools for parsing and extracting API specifications from various document formats (OpenAPI, Swagger, Postman, HAR, Word).",
            notes="""# Document Parsing Guidelines
When users upload API documentation:
1. Use `read_document` to load the document content first
2. Call `extract_api_spec` to parse and extract API specifications
3. Use `validate_api_spec` to ensure the extracted spec is valid and complete

# Workflow
- Read document → Extract API spec → Validate spec → Return parsed results
- Support multiple formats: OpenAPI/Swagger, Postman Collection, HAR, Word documents
- Handle parsing errors gracefully and provide clear feedback

# Error Handling
- If you encounter FunctionInactiveError, call `equip_tool_group("document_parser_tools")` to activate this group
- The tool group name in the error message is the exact parameter for activation

# Best Practices
- Always validate the extracted API spec before proceeding to test case generation
- Provide clear error messages if document format is unsupported or malformed""",
            tools=[
                doc_parser.get("read_document"),
                doc_parser.get("extract_api_spec"),
                doc_parser.get("validate_api_spec"),
            ],
        ),
        ToolGroupDefinition(
            group_name="testcase_generator_tools",
            description="Tools for generating comprehensive test cases including positive, negative, and security test scenarios.",
            notes="""# Test Case Generation Guidelines
After extracting API specifications:
1. Use `generate_positive_cases` to create happy-path test cases
2. Use `generate_negative_cases` to create error-handling test cases
3. Use `generate_security_cases` to create security-focused test cases

# Workflow
- Parse API spec → Generate positive cases → Generate negative cases → Generate security cases
- Ensure comprehensive coverage: happy path, edge cases, error scenarios, security vulnerabilities

# Error Handling
- If you encounter FunctionInactiveError, call `equip_tool_group("testcase_generator_tools")` to activate this group
- The tool group name in the error message is the exact parameter for activation

# Best Practices
- Generate balanced test suites covering all API endpoints
- Consider data types, boundaries, authentication, and authorization""",
            tools=[
                case_generator.get("generate_positive_cases"),
                case_generator.get("generate_negative_cases"),
                case_generator.get("generate_security_cases"),
            ],
        ),
        ToolGroupDefinition(
            group_name="test_executor_tools",
            description="Tools for executing API tests, validating responses, and capturing performance metrics.",
            notes="""# Test Execution Guidelines
After generating test cases:
1. Use `execute_api_test` to run test cases against target APIs
2. Use `validate_response` to verify response correctness (status, schema, data)
3. Use `capture_metrics` to collect performance metrics (latency, throughput)

# Workflow
- Execute test → Validate response → Capture metrics → Record results
- Support batch execution for multiple test cases
- Handle network errors and timeouts gracefully

# Error Handling
- If you encounter FunctionInactiveError, call `equip_tool_group("test_executor_tools")` to activate this group
- The tool group name in the error message is the exact parameter for activation

# Best Practices
- Execute tests in isolated environments when possible
- Validate both functional correctness and non-functional properties
- Capture detailed metrics for performance analysis
- Report clear failure reasons with context""",
            tools=[
                test_executor.get("execute_api_test"),
                test_executor.get("validate_response"),
                test_executor.get("capture_metrics"),
            ],
        ),
        ToolGroupDefinition(
            group_name="report_generator_tools",
            description="Tools for generating test reports, diagnosing failures, and suggesting improvements.",
            notes="""# Report Generation Guidelines
After test execution:
1. Use `generate_test_report` to create comprehensive test reports
2. Use `diagnose_failures` to analyze failed test cases and identify root causes
3. Use `suggest_improvements` to provide actionable recommendations

# Workflow
- Collect results → Generate report → Diagnose failures → Suggest improvements
- Include statistics: pass rate, coverage, performance metrics
- Provide clear visualizations and summaries

# Error Handling
- If you encounter FunctionInactiveError, call `equip_tool_group("report_generator_tools")` to activate this group
- The tool group name in the error message is the exact parameter for activation

# Best Practices
- Generate reports in multiple formats (HTML, JSON, Markdown)
- Highlight critical failures and performance bottlenecks
- Provide context-aware improvement suggestions
- Link failures to specific test cases and API endpoints""",
            tools=[
                report_tools.get("generate_test_report"),
                report_tools.get("diagnose_failures"),
                report_tools.get("suggest_improvements"),
            ],
        ),
    ]
