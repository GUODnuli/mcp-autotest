# -*- coding: utf-8 -*-
"""
测试报告工具集

提供报告生成、失败诊断、改进建议等功能。
复用 ReportGenerator 生成专业的测试报告。
"""

import json
from typing import Any, Dict, List, Optional
from pathlib import Path
from datetime import datetime
import uuid

from agentscope.tool import ToolResponse
from agentscope.message import TextBlock

# 导入项目模块
import sys
PROJECT_ROOT = Path(__file__).parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from common.test_models import (
    TestReport,
    TestResult,
    TestCaseStatus,
    AssertionResult,
    Assertion,
    AssertionType,
    AssertionOperator
)
from common.report_generator import ReportGenerator


def generate_test_report(
    results_json: str,
    report_format: str = "markdown",
    task_id: str = ""
) -> ToolResponse:
    """
    Generate a test report from test results.
    
    Creates a comprehensive test report in markdown or HTML format,
    including summary statistics, detailed results, and performance metrics.
    
    Args:
        results_json: JSON string of test results list. Each result should contain:
            - testcase_id: Test case identifier
            - interface_name: API name
            - test_status: "PASSED" | "FAILED" | "ERROR" | "SKIPPED"
            - duration: Execution time in seconds
            - request: Request details (method, url, body)
            - response: Response details (status_code, body)
            - assertion_results: List of assertion results
            - error_message: Error description (if any)
        report_format: Output format - "markdown" or "html" (default: "markdown")
        task_id: Optional task identifier for the report
    
    Returns:
        ToolResponse containing the generated report:
        {
            "status": "success",
            "report": "...",  # Markdown or HTML content
            "summary": {
                "total": 10,
                "passed": 8,
                "failed": 1,
                "error": 1,
                "pass_rate": 80.0
            }
        }
    """
    try:
        results = json.loads(results_json) if isinstance(results_json, str) else results_json
        
        if not results:
            return ToolResponse(
                content=[TextBlock(
                    type="text",
                    text=json.dumps({
                        "status": "warning",
                        "message": "No test results to generate report",
                        "report": "",
                        "summary": {}
                    }, ensure_ascii=False)
                )]
            )
        
        # 转换为 TestResult 对象列表
        test_results = []
        for r in results:
            # 构建 AssertionResult 列表
            assertion_results = []
            for ar in r.get("assertion_results", []):
                assertion = Assertion(
                    type=AssertionType(ar.get("type", "status_code")),
                    expected=ar.get("expected"),
                    actual_path=ar.get("actual_path"),
                    operator=AssertionOperator(ar.get("operator", "eq"))
                )
                assertion_results.append(AssertionResult(
                    assertion=assertion,
                    passed=ar.get("passed", False),
                    actual_value=ar.get("actual"),
                    error_message=ar.get("error_message")
                ))
            
            # 映射状态
            status_map = {
                "PASSED": TestCaseStatus.PASSED,
                "FAILED": TestCaseStatus.FAILED,
                "ERROR": TestCaseStatus.ERROR,
                "SKIPPED": TestCaseStatus.SKIPPED,
                "RUNNING": TestCaseStatus.RUNNING,
                "PENDING": TestCaseStatus.PENDING
            }
            status_str = r.get("test_status") or r.get("status", "PENDING")
            status = status_map.get(status_str.upper(), TestCaseStatus.PENDING)
            
            test_result = TestResult(
                testcase_id=r.get("testcase_id", str(uuid.uuid4())),
                interface_name=r.get("interface_name", "Unknown"),
                status=status,
                duration=r.get("duration", 0),
                request_log=r.get("request", {}),
                response_log=r.get("response"),
                assertion_results=assertion_results,
                error_message=r.get("error_message")
            )
            test_results.append(test_result)
        
        # 统计摘要
        total = len(test_results)
        passed = sum(1 for r in test_results if r.status == TestCaseStatus.PASSED)
        failed = sum(1 for r in test_results if r.status == TestCaseStatus.FAILED)
        error = sum(1 for r in test_results if r.status == TestCaseStatus.ERROR)
        skipped = sum(1 for r in test_results if r.status == TestCaseStatus.SKIPPED)
        
        pass_rate = round((passed / total) * 100, 2) if total > 0 else 0
        total_duration = sum(r.duration for r in test_results)
        
        # 最慢用例
        sorted_by_duration = sorted(test_results, key=lambda x: x.duration, reverse=True)
        slowest_testcases = [
            {
                "testcase_id": r.testcase_id,
                "interface_name": r.interface_name,
                "duration": round(r.duration, 3)
            }
            for r in sorted_by_duration[:10]
        ]
        
        # 错误模式分析
        error_patterns = _analyze_error_patterns(test_results)
        
        # 创建 TestReport 对象
        report = TestReport(
            task_id=task_id or str(uuid.uuid4()),
            total_count=total,
            passed_count=passed,
            failed_count=failed,
            error_count=error,
            skipped_count=skipped,
            pass_rate=pass_rate,
            total_duration=total_duration,
            testcase_results=test_results,
            slowest_testcases=slowest_testcases,
            error_patterns=error_patterns
        )
        
        # 生成报告
        generator = ReportGenerator()
        
        if report_format.lower() == "html":
            report_content = generator.generate_html(report)
        else:
            report_content = generator.generate_markdown(report)
        
        return ToolResponse(
            content=[TextBlock(
                type="text",
                text=json.dumps({
                    "status": "success",
                    "format": report_format,
                    "report": report_content,
                    "summary": {
                        "total": total,
                        "passed": passed,
                        "failed": failed,
                        "error": error,
                        "skipped": skipped,
                        "pass_rate": pass_rate,
                        "total_duration": round(total_duration, 3)
                    }
                }, ensure_ascii=False)
            )]
        )
    
    except Exception as e:
        return ToolResponse(
            content=[TextBlock(
                type="text",
                text=json.dumps({
                    "status": "error",
                    "error_code": "REPORT_GENERATION_ERROR",
                    "message": f"Failed to generate report: {str(e)}"
                }, ensure_ascii=False)
            )]
        )


def diagnose_failures(results_json: str) -> ToolResponse:
    """
    Diagnose and analyze test failures to identify root causes.
    
    Analyzes failed test results to categorize errors, identify patterns,
    and suggest potential root causes.
    
    Args:
        results_json: JSON string of test results list
    
    Returns:
        ToolResponse containing diagnosis:
        {
            "status": "success",
            "diagnosis": {
                "total_failures": 5,
                "categories": {
                    "connection_error": {"count": 2, "examples": [...]},
                    "assertion_failure": {"count": 3, "examples": [...]}
                },
                "root_causes": [
                    {"cause": "Service unavailable", "confidence": 0.9, "affected_tests": 2},
                    ...
                ],
                "patterns": [...]
            }
        }
    """
    try:
        results = json.loads(results_json) if isinstance(results_json, str) else results_json
        
        # 筛选失败和错误的用例
        failures = [
            r for r in results
            if r.get("test_status") in ["FAILED", "ERROR"]
            or r.get("status") in ["FAILED", "ERROR"]
        ]
        
        if not failures:
            return ToolResponse(
                content=[TextBlock(
                    type="text",
                    text=json.dumps({
                        "status": "success",
                        "message": "No failures to diagnose - all tests passed!",
                        "diagnosis": {
                            "total_failures": 0,
                            "categories": {},
                            "root_causes": [],
                            "patterns": []
                        }
                    }, ensure_ascii=False)
                )]
            )
        
        # 错误分类
        categories = {}
        for r in failures:
            error_msg = r.get("error_message", "")
            category = _classify_error_type(error_msg, r)
            
            if category not in categories:
                categories[category] = {
                    "count": 0,
                    "examples": []
                }
            
            categories[category]["count"] += 1
            if len(categories[category]["examples"]) < 3:  # 最多保留3个示例
                categories[category]["examples"].append({
                    "testcase_id": r.get("testcase_id", ""),
                    "interface_name": r.get("interface_name", ""),
                    "error_message": error_msg[:200]
                })
        
        # 根因分析
        root_causes = _analyze_root_causes(failures, categories)
        
        # 模式识别
        patterns = _identify_patterns(failures)
        
        return ToolResponse(
            content=[TextBlock(
                type="text",
                text=json.dumps({
                    "status": "success",
                    "diagnosis": {
                        "total_failures": len(failures),
                        "categories": categories,
                        "root_causes": root_causes,
                        "patterns": patterns
                    }
                }, ensure_ascii=False)
            )]
        )
    
    except Exception as e:
        return ToolResponse(
            content=[TextBlock(
                type="text",
                text=json.dumps({
                    "status": "error",
                    "error_code": "DIAGNOSIS_ERROR",
                    "message": f"Failed to diagnose failures: {str(e)}"
                }, ensure_ascii=False)
            )]
        )


def suggest_improvements(diagnosis_json: str) -> ToolResponse:
    """
    Generate improvement suggestions based on failure diagnosis.
    
    Analyzes the diagnosis results and provides actionable recommendations
    to fix issues and improve test reliability.
    
    Args:
        diagnosis_json: JSON string of diagnosis result (output of diagnose_failures)
    
    Returns:
        ToolResponse containing suggestions:
        {
            "status": "success",
            "suggestions": [
                {
                    "priority": "high",
                    "category": "connection_error",
                    "title": "Check service availability",
                    "description": "...",
                    "action_items": [...]
                },
                ...
            ],
            "summary": "..."
        }
    """
    try:
        diagnosis = json.loads(diagnosis_json) if isinstance(diagnosis_json, str) else diagnosis_json
        
        # 如果传入的是完整响应，提取 diagnosis 部分
        if "diagnosis" in diagnosis:
            diagnosis = diagnosis["diagnosis"]
        
        suggestions = []
        categories = diagnosis.get("categories", {})
        root_causes = diagnosis.get("root_causes", [])
        total_failures = diagnosis.get("total_failures", 0)
        
        if total_failures == 0:
            return ToolResponse(
                content=[TextBlock(
                    type="text",
                    text=json.dumps({
                        "status": "success",
                        "suggestions": [],
                        "summary": "No failures detected. All tests passed successfully!"
                    }, ensure_ascii=False)
                )]
            )
        
        # 根据错误类别生成建议
        suggestion_templates = {
            "connection_error": {
                "priority": "high",
                "title": "Fix Connection Issues",
                "description": "Multiple tests failed due to connection errors. The target service may be unavailable or unreachable.",
                "action_items": [
                    "Verify the target service is running and accessible",
                    "Check network connectivity and firewall rules",
                    "Verify the base URL is correctly configured",
                    "Increase connection timeout if needed"
                ]
            },
            "timeout": {
                "priority": "high",
                "title": "Address Timeout Issues",
                "description": "Tests are timing out. The service may be slow or overloaded.",
                "action_items": [
                    "Increase test timeout configuration",
                    "Check server performance and resource usage",
                    "Optimize slow API endpoints",
                    "Consider implementing request pagination"
                ]
            },
            "authentication": {
                "priority": "high",
                "title": "Fix Authentication Errors",
                "description": "Tests are failing due to authentication issues (401/403).",
                "action_items": [
                    "Verify API credentials are correct and not expired",
                    "Check if authentication tokens are being included in requests",
                    "Ensure proper authentication headers are set",
                    "Review API key or OAuth configuration"
                ]
            },
            "assertion_failure": {
                "priority": "medium",
                "title": "Review Failed Assertions",
                "description": "Some tests failed because the response didn't match expected values.",
                "action_items": [
                    "Review expected values in test assertions",
                    "Check if API behavior has changed",
                    "Verify business logic implementation",
                    "Update test expectations if requirements changed"
                ]
            },
            "not_found": {
                "priority": "medium",
                "title": "Fix Resource Not Found Errors",
                "description": "Tests are receiving 404 errors. Endpoints may be incorrect or resources don't exist.",
                "action_items": [
                    "Verify API endpoint paths are correct",
                    "Check if the API version has changed",
                    "Ensure test data (IDs, resources) exists",
                    "Review API documentation for correct paths"
                ]
            },
            "server_error": {
                "priority": "high",
                "title": "Investigate Server Errors",
                "description": "The server is returning 5xx errors. This indicates server-side issues.",
                "action_items": [
                    "Check server logs for detailed error information",
                    "Review recent code changes that might cause issues",
                    "Verify database connections and external dependencies",
                    "Test the API manually to reproduce the error"
                ]
            },
            "validation_error": {
                "priority": "medium",
                "title": "Fix Request Validation Errors",
                "description": "Requests are being rejected due to invalid parameters.",
                "action_items": [
                    "Review request body structure and required fields",
                    "Check parameter types and formats",
                    "Validate enum values match API specification",
                    "Update test cases with correct parameter values"
                ]
            }
        }
        
        # 生成建议
        for category, data in categories.items():
            if category in suggestion_templates:
                template = suggestion_templates[category]
                suggestion = {
                    "priority": template["priority"],
                    "category": category,
                    "title": template["title"],
                    "description": template["description"],
                    "affected_count": data["count"],
                    "action_items": template["action_items"],
                    "examples": data.get("examples", [])[:2]
                }
                suggestions.append(suggestion)
            else:
                # 通用建议
                suggestion = {
                    "priority": "low",
                    "category": category,
                    "title": f"Review {category.replace('_', ' ').title()} Issues",
                    "description": f"{data['count']} tests failed with {category} errors.",
                    "affected_count": data["count"],
                    "action_items": [
                        "Review error messages for specific details",
                        "Check test case configuration",
                        "Verify API implementation"
                    ],
                    "examples": data.get("examples", [])[:2]
                }
                suggestions.append(suggestion)
        
        # 根据根因添加额外建议
        for cause in root_causes:
            if cause.get("confidence", 0) >= 0.8:
                suggestions.append({
                    "priority": "high",
                    "category": "root_cause",
                    "title": cause.get("cause", "Identified Root Cause"),
                    "description": f"High confidence ({cause.get('confidence', 0)*100:.0f}%) root cause affecting {cause.get('affected_tests', 0)} tests.",
                    "affected_count": cause.get("affected_tests", 0),
                    "action_items": cause.get("recommendations", [
                        "Address this root cause first as it affects multiple tests"
                    ])
                })
        
        # 按优先级排序
        priority_order = {"high": 0, "medium": 1, "low": 2}
        suggestions.sort(key=lambda x: priority_order.get(x["priority"], 3))
        
        # 生成总结
        high_priority = sum(1 for s in suggestions if s["priority"] == "high")
        summary = f"Found {len(suggestions)} areas for improvement. "
        if high_priority > 0:
            summary += f"{high_priority} high-priority issues require immediate attention. "
        summary += f"Total {total_failures} test failures need to be addressed."
        
        return ToolResponse(
            content=[TextBlock(
                type="text",
                text=json.dumps({
                    "status": "success",
                    "suggestions": suggestions,
                    "summary": summary,
                    "total_suggestions": len(suggestions),
                    "high_priority_count": high_priority
                }, ensure_ascii=False)
            )]
        )
    
    except Exception as e:
        return ToolResponse(
            content=[TextBlock(
                type="text",
                text=json.dumps({
                    "status": "error",
                    "error_code": "SUGGESTION_ERROR",
                    "message": f"Failed to generate suggestions: {str(e)}"
                }, ensure_ascii=False)
            )]
        )


# ============= 辅助函数 =============

def _analyze_error_patterns(test_results: List[TestResult]) -> List[Dict[str, Any]]:
    """分析错误模式"""
    error_messages = {}
    
    for r in test_results:
        if r.status in [TestCaseStatus.FAILED, TestCaseStatus.ERROR] and r.error_message:
            # 简化错误信息作为模式
            pattern = _simplify_error_message(r.error_message)
            if pattern not in error_messages:
                error_messages[pattern] = {
                    "pattern": pattern,
                    "count": 0,
                    "example_id": r.testcase_id
                }
            error_messages[pattern]["count"] += 1
    
    # 按出现次数排序
    patterns = sorted(error_messages.values(), key=lambda x: x["count"], reverse=True)
    return patterns[:10]


def _simplify_error_message(msg: str) -> str:
    """简化错误信息以识别模式"""
    # 移除具体值，保留模式
    import re
    
    # 移除 UUID
    msg = re.sub(r'[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}', '<UUID>', msg)
    # 移除 IP 地址
    msg = re.sub(r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}', '<IP>', msg)
    # 移除端口号
    msg = re.sub(r':\d{2,5}', ':<PORT>', msg)
    # 移除具体数值
    msg = re.sub(r'\b\d+\.\d+\b', '<NUMBER>', msg)
    
    return msg[:100]


def _classify_error_type(error_msg: str, result: Dict) -> str:
    """分类错误类型"""
    error_lower = error_msg.lower()
    
    # 检查响应状态码
    response = result.get("response", {})
    status_code = response.get("status_code", 0) if response else 0
    
    if status_code == 401 or "unauthorized" in error_lower:
        return "authentication"
    elif status_code == 403 or "forbidden" in error_lower:
        return "authorization"
    elif status_code == 404 or "not found" in error_lower:
        return "not_found"
    elif status_code >= 500:
        return "server_error"
    elif status_code == 400 or "bad request" in error_lower or "validation" in error_lower:
        return "validation_error"
    elif "timeout" in error_lower:
        return "timeout"
    elif "connection" in error_lower or "refused" in error_lower or "unreachable" in error_lower:
        return "connection_error"
    elif "assertion" in error_lower or "断言" in error_lower:
        return "assertion_failure"
    else:
        return "other"


def _analyze_root_causes(failures: List[Dict], categories: Dict) -> List[Dict]:
    """分析根因"""
    root_causes = []
    
    # 连接错误 -> 服务不可用
    if categories.get("connection_error", {}).get("count", 0) > 0:
        count = categories["connection_error"]["count"]
        root_causes.append({
            "cause": "Service Unavailable",
            "confidence": min(0.9, count / len(failures)),
            "affected_tests": count,
            "recommendations": [
                "Verify the target service is running",
                "Check network connectivity",
                "Review service health status"
            ]
        })
    
    # 认证错误 -> 凭证问题
    if categories.get("authentication", {}).get("count", 0) > 0:
        count = categories["authentication"]["count"]
        root_causes.append({
            "cause": "Authentication Credential Issues",
            "confidence": 0.85,
            "affected_tests": count,
            "recommendations": [
                "Verify API credentials are valid",
                "Check if tokens have expired",
                "Ensure authentication headers are set correctly"
            ]
        })
    
    # 大量断言失败 -> 业务逻辑变更
    if categories.get("assertion_failure", {}).get("count", 0) >= 3:
        count = categories["assertion_failure"]["count"]
        root_causes.append({
            "cause": "Business Logic or API Response Changed",
            "confidence": 0.7,
            "affected_tests": count,
            "recommendations": [
                "Review recent API or business logic changes",
                "Update test expectations if requirements changed",
                "Verify data consistency"
            ]
        })
    
    return root_causes


def _identify_patterns(failures: List[Dict]) -> List[Dict]:
    """识别失败模式"""
    patterns = []
    
    # 检查是否所有失败都是同一接口
    interfaces = [f.get("interface_name", "") for f in failures]
    from collections import Counter
    interface_counts = Counter(interfaces)
    
    for interface, count in interface_counts.most_common(3):
        if count >= 2:
            patterns.append({
                "type": "interface_pattern",
                "description": f"Multiple failures on '{interface}' interface ({count} tests)",
                "affected_interface": interface,
                "count": count
            })
    
    # 检查时间模式（如果有时间戳）
    # ...
    
    return patterns
