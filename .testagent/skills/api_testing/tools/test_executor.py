# -*- coding: utf-8 -*-
"""
测试执行工具集

提供API测试执行、响应验证、性能指标采集等功能。
复用 RequestsEngine 实现HTTP请求发送和断言验证。
"""

import json
import time
from typing import Any, Dict, List, Optional
from pathlib import Path

from agentscope.tool import ToolResponse
from agentscope.message import TextBlock

# 导入项目模块
import sys
PROJECT_ROOT = Path(__file__).parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from common.test_models import (
    TestCase,
    TestResult,
    Request,
    Response,
    Assertion,
    AssertionType,
    AssertionOperator,
    TestCaseStatus
)
from common.engines.requests_engine import RequestsEngine

# 默认配置
DEFAULT_BASE_URL = "http://localhost:8080"
DEFAULT_TIMEOUT = 30


def execute_api_test(testcase_json: str, base_url: str = "") -> ToolResponse:
    """
    Execute a single API test case.
    
    Sends HTTP request based on test case definition and returns
    execution result with response details.
    
    Args:
        testcase_json: JSON string of test case definition. Required fields:
            - interface_name: Name of the API interface
            - interface_path: API endpoint path (e.g., "/calculate_rate")
            - request: Request object with method, url, headers, body
            - assertions: List of assertion rules (optional)
        base_url: Base URL for the API server (e.g., "http://localhost:8080").
                  If empty, defaults to "http://localhost:8080"
    
    Returns:
        ToolResponse containing test execution result:
        {
            "status": "success",
            "testcase_id": "...",
            "test_status": "PASSED" | "FAILED" | "ERROR",
            "duration": 0.123,
            "response": {...},
            "assertion_results": [...]
        }
    
    Example:
        testcase = {
            "interface_name": "Calculate Rate",
            "interface_path": "/calculate_rate",
            "request": {
                "method": "POST",
                "url": "/calculate_rate",
                "body": {"term": "12", "repayment_method": "equal_principal_interest"}
            },
            "assertions": [
                {"type": "status_code", "expected": 200, "operator": "eq"}
            ]
        }
        execute_api_test(json.dumps(testcase), "http://localhost:8080")
    """
    engine = None
    try:
        # 解析测试用例
        testcase_dict = json.loads(testcase_json) if isinstance(testcase_json, str) else testcase_json
        
        # 设置 base_url 默认值（根据经验教训）
        if not base_url:
            base_url = DEFAULT_BASE_URL
        
        # 确保 base_url 没有尾部斜杠
        base_url = base_url.rstrip("/")
        
        # 构建完整 URL
        request_data = testcase_dict.get("request", {})
        endpoint = request_data.get("url") or testcase_dict.get("interface_path", "")
        
        # 检查 endpoint 是否已经是完整 URL（包含 http:// 或 https://）
        if endpoint.startswith(("http://", "https://")):
            # 已经是完整 URL，直接使用
            full_url = endpoint
        else:
            # 相对路径，需要拼接 base_url
            # 确保 endpoint 以 / 开头
            if endpoint and not endpoint.startswith("/"):
                endpoint = "/" + endpoint
            
            full_url = f"{base_url}{endpoint}"
        
        request_data["url"] = full_url
        
        # 构建 TestCase 对象
        request = Request(
            method=request_data.get("method", "GET").upper(),
            url=full_url,
            headers=request_data.get("headers"),
            query_params=request_data.get("query_params"),
            body=request_data.get("body"),
            timeout=request_data.get("timeout", DEFAULT_TIMEOUT)
        )
        
        # 解析断言
        assertions = []
        for assertion_dict in testcase_dict.get("assertions", []):
            assertion = _parse_assertion(assertion_dict)
            if assertion:
                assertions.append(assertion)
        
        # 默认添加状态码断言
        if not assertions:
            assertions.append(Assertion(
                type=AssertionType.STATUS_CODE,
                expected=200,
                operator=AssertionOperator.EQ,
                description="Default: expect HTTP 200"
            ))
        
        testcase = TestCase(
            id=testcase_dict.get("id", ""),
            interface_name=testcase_dict.get("interface_name", "Unknown API"),
            interface_path=endpoint,
            request=request,
            assertions=assertions,
            priority=testcase_dict.get("priority", "medium"),
            tags=testcase_dict.get("tags", []),
            description=testcase_dict.get("description")
        )
        
        # 初始化并执行引擎
        engine = RequestsEngine()
        engine.initialize({
            "log_level": "INFO",
            "max_retries": 3,
            "retry_delay": 1,
            "verify_ssl": False,
            "default_timeout": DEFAULT_TIMEOUT
        })
        
        # 执行测试
        result = engine.execute_testcase(testcase)
        
        # 构建返回结果
        assertion_results = []
        for ar in result.assertion_results:
            assertion_results.append({
                "type": ar.assertion.type.value if hasattr(ar.assertion.type, 'value') else str(ar.assertion.type),
                "expected": ar.assertion.expected,
                "actual": ar.actual_value,
                "passed": ar.passed,
                "error_message": ar.error_message
            })
        
        return ToolResponse(
            content=[TextBlock(
                type="text",
                text=json.dumps({
                    "status": "success",
                    "testcase_id": result.testcase_id,
                    "interface_name": result.interface_name,
                    "test_status": result.status.value if hasattr(result.status, 'value') else str(result.status),
                    "duration": round(result.duration, 3),
                    "request": {
                        "method": request.method,
                        "url": request.url,
                        "headers": request.headers,
                        "body": request.body
                    },
                    "response": result.response_log,
                    "assertion_results": assertion_results,
                    "error_message": result.error_message
                }, ensure_ascii=False, default=str)
            )]
        )
    
    except json.JSONDecodeError as e:
        return ToolResponse(
            content=[TextBlock(
                type="text",
                text=json.dumps({
                    "status": "error",
                    "error_code": "INVALID_JSON",
                    "message": f"Invalid test case JSON: {str(e)}"
                }, ensure_ascii=False)
            )]
        )
    
    except Exception as e:
        return ToolResponse(
            content=[TextBlock(
                type="text",
                text=json.dumps({
                    "status": "error",
                    "error_code": "EXECUTION_ERROR",
                    "message": f"Test execution failed: {str(e)}",
                    "hint": "Check if the target service is running and accessible"
                }, ensure_ascii=False)
            )]
        )
    
    finally:
        if engine:
            engine.cleanup()


def _parse_assertion(assertion_dict: Dict[str, Any]) -> Optional[Assertion]:
    """解析断言字典为 Assertion 对象"""
    try:
        # 操作符映射（处理自然语言风格的操作符）
        operator_mapping = {
            "equals": "eq",
            "equal": "eq",
            "eq": "eq",
            "not_equals": "ne",
            "not_equal": "ne",
            "ne": "ne",
            "greater_than": "gt",
            "greater": "gt",
            "gt": "gt",
            "less_than": "lt",
            "less": "lt",
            "lt": "lt",
            "gte": "gte",
            "lte": "lte",
            "in": "in",
            "contains": "in",
            "not_in": "not_in"
        }
        
        # 断言类型映射
        type_mapping = {
            "status_code": AssertionType.STATUS_CODE,
            "statuscode": AssertionType.STATUS_CODE,
            "status": AssertionType.STATUS_CODE,
            "json_path": AssertionType.JSON_PATH,
            "jsonpath": AssertionType.JSON_PATH,
            "regex": AssertionType.REGEX,
            "contains": AssertionType.CONTAINS,
            "equals": AssertionType.EQUALS,
            "equal": AssertionType.EQUALS,
            "not_equals": AssertionType.NOT_EQUALS,
            "greater_than": AssertionType.GREATER_THAN,
            "less_than": AssertionType.LESS_THAN
        }
        
        assertion_type_str = assertion_dict.get("type", "status_code").lower()
        assertion_type = type_mapping.get(assertion_type_str, AssertionType.STATUS_CODE)
        
        operator_str = assertion_dict.get("operator", "eq").lower()
        operator = AssertionOperator(operator_mapping.get(operator_str, "eq"))
        
        return Assertion(
            type=assertion_type,
            expected=assertion_dict.get("expected"),
            actual_path=assertion_dict.get("actual_path"),
            operator=operator,
            description=assertion_dict.get("description")
        )
    except Exception:
        return None


def validate_response(response_json: str, assertions_json: str) -> ToolResponse:
    """
    Validate API response against assertion rules.
    
    Performs validation of response data against provided assertions
    without sending a new request. Useful for re-validating cached responses.
    
    Args:
        response_json: JSON string of response object with fields:
            - status_code: HTTP status code
            - headers: Response headers dict
            - body: Response body (dict or string)
            - elapsed: Response time in seconds
        assertions_json: JSON string of assertion rules list
    
    Returns:
        ToolResponse containing validation results:
        {
            "status": "success",
            "all_passed": true,
            "passed_count": 3,
            "failed_count": 0,
            "results": [...]
        }
    """
    engine = None
    try:
        response_dict = json.loads(response_json) if isinstance(response_json, str) else response_json
        assertions_list = json.loads(assertions_json) if isinstance(assertions_json, str) else assertions_json
        
        # 构建 Response 对象
        response = Response(
            status_code=response_dict.get("status_code", 0),
            headers=response_dict.get("headers", {}),
            body=response_dict.get("body", {}),
            elapsed=response_dict.get("elapsed", 0)
        )
        
        # 解析断言
        assertions = []
        for assertion_dict in assertions_list:
            assertion = _parse_assertion(assertion_dict)
            if assertion:
                assertions.append(assertion)
        
        if not assertions:
            return ToolResponse(
                content=[TextBlock(
                    type="text",
                    text=json.dumps({
                        "status": "warning",
                        "message": "No valid assertions provided",
                        "all_passed": True,
                        "results": []
                    }, ensure_ascii=False)
                )]
            )
        
        # 初始化引擎进行验证
        engine = RequestsEngine()
        engine.initialize({"log_level": "WARNING"})
        
        # 执行验证
        results = engine.validate_assertions(response, assertions)
        
        # 构建返回结果
        validation_results = []
        passed_count = 0
        for ar in results:
            passed = ar.passed
            if passed:
                passed_count += 1
            validation_results.append({
                "type": ar.assertion.type.value if hasattr(ar.assertion.type, 'value') else str(ar.assertion.type),
                "expected": ar.assertion.expected,
                "actual": ar.actual_value,
                "passed": passed,
                "error_message": ar.error_message
            })
        
        all_passed = passed_count == len(results)
        
        return ToolResponse(
            content=[TextBlock(
                type="text",
                text=json.dumps({
                    "status": "success",
                    "all_passed": all_passed,
                    "passed_count": passed_count,
                    "failed_count": len(results) - passed_count,
                    "total_assertions": len(results),
                    "results": validation_results
                }, ensure_ascii=False, default=str)
            )]
        )
    
    except json.JSONDecodeError as e:
        return ToolResponse(
            content=[TextBlock(
                type="text",
                text=json.dumps({
                    "status": "error",
                    "error_code": "INVALID_JSON",
                    "message": f"Invalid JSON input: {str(e)}"
                }, ensure_ascii=False)
            )]
        )
    
    except Exception as e:
        return ToolResponse(
            content=[TextBlock(
                type="text",
                text=json.dumps({
                    "status": "error",
                    "error_code": "VALIDATION_ERROR",
                    "message": f"Response validation failed: {str(e)}"
                }, ensure_ascii=False)
            )]
        )
    
    finally:
        if engine:
            engine.cleanup()


def capture_metrics(results_json: str) -> ToolResponse:
    """
    Capture and summarize performance metrics from test results.
    
    Analyzes test results to provide performance statistics including
    response times, success rates, and error distribution.
    
    Args:
        results_json: JSON string of test results list. Each result should contain:
            - testcase_id: Test case identifier
            - interface_name: API name
            - test_status: "PASSED" | "FAILED" | "ERROR"
            - duration: Execution time in seconds
            - error_message: Error description (if any)
    
    Returns:
        ToolResponse containing metrics summary:
        {
            "status": "success",
            "summary": {
                "total_tests": 10,
                "passed": 8,
                "failed": 1,
                "error": 1,
                "pass_rate": 80.0,
                "avg_duration": 0.234,
                "min_duration": 0.102,
                "max_duration": 0.567
            },
            "slowest_tests": [...],
            "error_distribution": {...}
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
                        "message": "No test results provided",
                        "summary": {}
                    }, ensure_ascii=False)
                )]
            )
        
        # 统计指标
        total = len(results)
        passed = sum(1 for r in results if r.get("test_status") == "PASSED" or r.get("status") == "PASSED")
        failed = sum(1 for r in results if r.get("test_status") == "FAILED" or r.get("status") == "FAILED")
        error = sum(1 for r in results if r.get("test_status") == "ERROR" or r.get("status") == "ERROR")
        
        # 耗时统计
        durations = [r.get("duration", 0) for r in results if r.get("duration")]
        avg_duration = sum(durations) / len(durations) if durations else 0
        min_duration = min(durations) if durations else 0
        max_duration = max(durations) if durations else 0
        
        # 最慢测试 Top 5
        sorted_by_duration = sorted(results, key=lambda x: x.get("duration", 0), reverse=True)
        slowest_tests = [
            {
                "testcase_id": r.get("testcase_id", ""),
                "interface_name": r.get("interface_name", ""),
                "duration": round(r.get("duration", 0), 3)
            }
            for r in sorted_by_duration[:5]
        ]
        
        # 错误分布
        error_distribution = {}
        for r in results:
            if r.get("error_message"):
                error_type = _classify_error(r["error_message"])
                error_distribution[error_type] = error_distribution.get(error_type, 0) + 1
        
        pass_rate = round((passed / total) * 100, 2) if total > 0 else 0
        
        return ToolResponse(
            content=[TextBlock(
                type="text",
                text=json.dumps({
                    "status": "success",
                    "summary": {
                        "total_tests": total,
                        "passed": passed,
                        "failed": failed,
                        "error": error,
                        "skipped": total - passed - failed - error,
                        "pass_rate": pass_rate,
                        "avg_duration": round(avg_duration, 3),
                        "min_duration": round(min_duration, 3),
                        "max_duration": round(max_duration, 3),
                        "total_duration": round(sum(durations), 3)
                    },
                    "slowest_tests": slowest_tests,
                    "error_distribution": error_distribution
                }, ensure_ascii=False)
            )]
        )
    
    except json.JSONDecodeError as e:
        return ToolResponse(
            content=[TextBlock(
                type="text",
                text=json.dumps({
                    "status": "error",
                    "error_code": "INVALID_JSON",
                    "message": f"Invalid results JSON: {str(e)}"
                }, ensure_ascii=False)
            )]
        )
    
    except Exception as e:
        return ToolResponse(
            content=[TextBlock(
                type="text",
                text=json.dumps({
                    "status": "error",
                    "error_code": "METRICS_ERROR",
                    "message": f"Failed to capture metrics: {str(e)}"
                }, ensure_ascii=False)
            )]
        )


def _classify_error(error_message: str) -> str:
    """对错误信息进行分类"""
    error_message_lower = error_message.lower()
    
    if "timeout" in error_message_lower:
        return "timeout"
    elif "connection" in error_message_lower or "refused" in error_message_lower:
        return "connection_error"
    elif "401" in error_message or "unauthorized" in error_message_lower:
        return "authentication"
    elif "403" in error_message or "forbidden" in error_message_lower:
        return "authorization"
    elif "404" in error_message or "not found" in error_message_lower:
        return "not_found"
    elif "500" in error_message or "internal server" in error_message_lower:
        return "server_error"
    elif "断言" in error_message or "assertion" in error_message_lower:
        return "assertion_failure"
    else:
        return "other"
