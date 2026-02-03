# -*- coding: utf-8 -*-
"""
测试用例生成工具集

提供正向用例、异常用例、安全测试用例生成，以及业务规则应用功能。
基于 API 规范自动生成覆盖全面的测试用例。
"""

import json
import uuid
import itertools
from typing import Any, Dict, List, Optional

from agentscope.tool import ToolResponse
from agentscope.message import TextBlock


def generate_positive_cases(api_spec_json: str, max_combinations: int = 20) -> ToolResponse:
    """
    Generate positive test cases from API specification.
    
    Creates test cases with valid parameter combinations based on
    parameter types and enum values defined in the API spec.
    
    Args:
        api_spec_json: JSON string of API specification containing:
            - endpoint: API endpoint path
            - method: HTTP method
            - request: Parameter definitions with types and enums
        max_combinations: Maximum number of test cases to generate (default 20)
    
    Returns:
        ToolResponse containing generated test cases:
        {
            "status": "success",
            "testcases": [...],
            "count": 10
        }
    
    Example:
        api_spec = {
            "endpoint": "/calculate_rate",
            "method": "POST",
            "request": {
                "term": {"type": "string", "enum": ["12", "24", "36"]},
                "repayment_method": {"type": "string", "enum": ["equal_principal_interest", "month_inter_pay"]},
                "use_coupon": {"type": "integer", "enum": [0, 20]}
            }
        }
        generate_positive_cases(json.dumps(api_spec))
    """
    try:
        spec = json.loads(api_spec_json) if isinstance(api_spec_json, str) else api_spec_json
        
        endpoint = spec.get("endpoint", "/api")
        method = spec.get("method", "POST").upper()
        request_params = spec.get("request", {})
        description = spec.get("description", "")
        
        if not request_params:
            # 无参数时生成单个测试用例
            testcase = _create_testcase(
                interface_name=f"Positive Test - {endpoint}",
                interface_path=endpoint,
                method=method,
                body={},
                description=f"Basic positive test for {endpoint}",
                tags=["positive", "basic"]
            )
            return ToolResponse(
                content=[TextBlock(
                    type="text",
                    text=json.dumps({
                        "status": "success",
                        "testcases": [testcase],
                        "count": 1,
                        "message": "No parameters defined, generated basic test case"
                    }, ensure_ascii=False)
                )]
            )
        
        # 提取枚举值和默认值
        param_values = {}
        for param_name, param_def in request_params.items():
            if isinstance(param_def, dict):
                if "enum" in param_def:
                    param_values[param_name] = param_def["enum"]
                else:
                    # 根据类型生成默认值
                    param_values[param_name] = [_get_default_value(param_def.get("type", "string"))]
            else:
                param_values[param_name] = [param_def]
        
        # 生成参数组合
        param_names = list(param_values.keys())
        param_value_lists = [param_values[name] for name in param_names]
        
        # 笛卡尔积（限制数量）
        all_combinations = list(itertools.product(*param_value_lists))
        if len(all_combinations) > max_combinations:
            # 采样策略：保留边界值组合 + 随机采样
            selected_combinations = _smart_sample(all_combinations, max_combinations)
        else:
            selected_combinations = all_combinations
        
        # 生成测试用例
        testcases = []
        for idx, combination in enumerate(selected_combinations, 1):
            body = dict(zip(param_names, combination))
            
            # 生成描述
            param_desc = ", ".join([f"{k}={v}" for k, v in body.items()])
            
            testcase = _create_testcase(
                interface_name=f"Positive Test #{idx} - {endpoint}",
                interface_path=endpoint,
                method=method,
                body=body,
                description=f"Valid parameter combination: {param_desc}",
                tags=["positive", "generated"],
                assertions=[
                    {"type": "status_code", "expected": 200, "operator": "eq"}
                ]
            )
            testcases.append(testcase)
        
        return ToolResponse(
            content=[TextBlock(
                type="text",
                text=json.dumps({
                    "status": "success",
                    "testcases": testcases,
                    "count": len(testcases),
                    "total_combinations": len(all_combinations),
                    "sampled": len(all_combinations) > max_combinations
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
                    "message": f"Invalid API spec JSON: {str(e)}"
                }, ensure_ascii=False)
            )]
        )
    
    except Exception as e:
        return ToolResponse(
            content=[TextBlock(
                type="text",
                text=json.dumps({
                    "status": "error",
                    "error_code": "GENERATION_ERROR",
                    "message": f"Failed to generate positive cases: {str(e)}"
                }, ensure_ascii=False)
            )]
        )


def generate_negative_cases(api_spec_json: str) -> ToolResponse:
    """
    Generate negative test cases for boundary and invalid inputs.
    
    Creates test cases with invalid parameters, boundary values,
    type mismatches, and missing required fields.
    
    Args:
        api_spec_json: JSON string of API specification
    
    Returns:
        ToolResponse containing negative test cases:
        {
            "status": "success",
            "testcases": [...],
            "categories": {
                "invalid_type": 3,
                "boundary_value": 2,
                "missing_param": 2,
                "invalid_enum": 3
            }
        }
    """
    try:
        spec = json.loads(api_spec_json) if isinstance(api_spec_json, str) else api_spec_json
        
        endpoint = spec.get("endpoint", "/api")
        method = spec.get("method", "POST").upper()
        request_params = spec.get("request", {})
        
        testcases = []
        categories = {
            "invalid_type": 0,
            "boundary_value": 0,
            "missing_param": 0,
            "invalid_enum": 0,
            "empty_value": 0
        }
        
        # 获取一个有效的基础参数组合
        base_body = {}
        for param_name, param_def in request_params.items():
            if isinstance(param_def, dict):
                if "enum" in param_def:
                    base_body[param_name] = param_def["enum"][0]
                else:
                    base_body[param_name] = _get_default_value(param_def.get("type", "string"))
        
        # 1. 无效类型测试
        for param_name, param_def in request_params.items():
            if not isinstance(param_def, dict):
                continue
            
            param_type = param_def.get("type", "string")
            invalid_values = _get_invalid_type_values(param_type)
            
            for invalid_value, desc in invalid_values:
                body = base_body.copy()
                body[param_name] = invalid_value
                
                testcase = _create_testcase(
                    interface_name=f"Negative - Invalid Type for {param_name}",
                    interface_path=endpoint,
                    method=method,
                    body=body,
                    description=f"Parameter '{param_name}' with invalid type: {desc}",
                    tags=["negative", "invalid_type"],
                    assertions=[
                        {"type": "status_code", "expected": 400, "operator": "eq"}
                    ]
                )
                testcases.append(testcase)
                categories["invalid_type"] += 1
        
        # 2. 无效枚举值测试
        for param_name, param_def in request_params.items():
            if not isinstance(param_def, dict) or "enum" not in param_def:
                continue
            
            body = base_body.copy()
            body[param_name] = "INVALID_ENUM_VALUE_12345"
            
            testcase = _create_testcase(
                interface_name=f"Negative - Invalid Enum for {param_name}",
                interface_path=endpoint,
                method=method,
                body=body,
                description=f"Parameter '{param_name}' with value not in enum",
                tags=["negative", "invalid_enum"],
                assertions=[
                    {"type": "status_code", "expected": 400, "operator": "eq"}
                ]
            )
            testcases.append(testcase)
            categories["invalid_enum"] += 1
        
        # 3. 缺失参数测试
        for param_name in request_params.keys():
            body = {k: v for k, v in base_body.items() if k != param_name}
            
            testcase = _create_testcase(
                interface_name=f"Negative - Missing {param_name}",
                interface_path=endpoint,
                method=method,
                body=body,
                description=f"Missing required parameter: {param_name}",
                tags=["negative", "missing_param"],
                assertions=[
                    {"type": "status_code", "expected": 400, "operator": "eq"}
                ]
            )
            testcases.append(testcase)
            categories["missing_param"] += 1
        
        # 4. 空值测试
        for param_name, param_def in request_params.items():
            body = base_body.copy()
            body[param_name] = ""
            
            testcase = _create_testcase(
                interface_name=f"Negative - Empty Value for {param_name}",
                interface_path=endpoint,
                method=method,
                body=body,
                description=f"Parameter '{param_name}' with empty string",
                tags=["negative", "empty_value"],
                assertions=[
                    {"type": "status_code", "expected": 400, "operator": "eq"}
                ]
            )
            testcases.append(testcase)
            categories["empty_value"] += 1
        
        # 5. 边界值测试（数字类型）
        for param_name, param_def in request_params.items():
            if not isinstance(param_def, dict):
                continue
            
            param_type = param_def.get("type", "string")
            if param_type in ["integer", "number"]:
                boundary_values = [
                    (-1, "negative number"),
                    (0, "zero"),
                    (999999999, "very large number"),
                    (-999999999, "very small number")
                ]
                
                for value, desc in boundary_values:
                    body = base_body.copy()
                    body[param_name] = value
                    
                    testcase = _create_testcase(
                        interface_name=f"Negative - Boundary for {param_name}",
                        interface_path=endpoint,
                        method=method,
                        body=body,
                        description=f"Boundary test: {param_name} = {value} ({desc})",
                        tags=["negative", "boundary_value"],
                        assertions=[
                            {"type": "status_code", "expected": 400, "operator": "in"}
                        ]
                    )
                    testcases.append(testcase)
                    categories["boundary_value"] += 1
        
        return ToolResponse(
            content=[TextBlock(
                type="text",
                text=json.dumps({
                    "status": "success",
                    "testcases": testcases,
                    "count": len(testcases),
                    "categories": categories
                }, ensure_ascii=False)
            )]
        )
    
    except Exception as e:
        return ToolResponse(
            content=[TextBlock(
                type="text",
                text=json.dumps({
                    "status": "error",
                    "error_code": "GENERATION_ERROR",
                    "message": f"Failed to generate negative cases: {str(e)}"
                }, ensure_ascii=False)
            )]
        )


def generate_security_cases(api_spec_json: str) -> ToolResponse:
    """
    Generate security test cases for common vulnerabilities.
    
    Creates test cases targeting SQL injection, XSS, command injection,
    and other OWASP Top 10 vulnerabilities.
    
    NOTE: These test cases are for defensive security testing only.
    They help identify and fix vulnerabilities in your own applications.
    
    Args:
        api_spec_json: JSON string of API specification
    
    Returns:
        ToolResponse containing security test cases:
        {
            "status": "success",
            "testcases": [...],
            "vulnerability_types": ["sql_injection", "xss", "command_injection"]
        }
    """
    try:
        spec = json.loads(api_spec_json) if isinstance(api_spec_json, str) else api_spec_json
        
        endpoint = spec.get("endpoint", "/api")
        method = spec.get("method", "POST").upper()
        request_params = spec.get("request", {})
        
        testcases = []
        vulnerability_types = set()
        
        # 获取基础参数
        base_body = {}
        string_params = []
        
        for param_name, param_def in request_params.items():
            if isinstance(param_def, dict):
                param_type = param_def.get("type", "string")
                if param_type == "string":
                    string_params.append(param_name)
                if "enum" in param_def:
                    base_body[param_name] = param_def["enum"][0]
                else:
                    base_body[param_name] = _get_default_value(param_type)
        
        # 安全测试 payload（仅用于防御性测试）
        security_payloads = {
            "sql_injection": [
                ("' OR '1'='1", "Basic SQL injection"),
                ("1; DROP TABLE users--", "SQL command injection"),
                ("' UNION SELECT * FROM users--", "SQL UNION injection")
            ],
            "xss": [
                ("<script>alert('xss')</script>", "Basic XSS"),
                ("javascript:alert('xss')", "JavaScript protocol XSS"),
                ("<img src=x onerror=alert('xss')>", "Event handler XSS")
            ],
            "path_traversal": [
                ("../../../etc/passwd", "Path traversal"),
                ("..\\..\\..\\windows\\system32\\config\\sam", "Windows path traversal")
            ],
            "special_chars": [
                ("\x00null\x00", "Null byte injection"),
                ("${7*7}", "Template injection"),
                ("{{7*7}}", "SSTI test")
            ]
        }
        
        # 为每个字符串参数生成安全测试
        for param_name in string_params:
            for vuln_type, payloads in security_payloads.items():
                for payload, desc in payloads:
                    body = base_body.copy()
                    body[param_name] = payload
                    
                    testcase = _create_testcase(
                        interface_name=f"Security - {vuln_type} on {param_name}",
                        interface_path=endpoint,
                        method=method,
                        body=body,
                        description=f"Security test ({desc}) for parameter '{param_name}'",
                        tags=["security", vuln_type],
                        assertions=[
                            # 安全测试期望服务器正确处理（400或200+无敏感数据泄露）
                            {"type": "status_code", "expected": 500, "operator": "ne",
                             "description": "Should not cause server error"}
                        ]
                    )
                    testcases.append(testcase)
                    vulnerability_types.add(vuln_type)
        
        return ToolResponse(
            content=[TextBlock(
                type="text",
                text=json.dumps({
                    "status": "success",
                    "testcases": testcases,
                    "count": len(testcases),
                    "vulnerability_types": list(vulnerability_types),
                    "note": "These security tests are for defensive testing to identify vulnerabilities in your own applications."
                }, ensure_ascii=False)
            )]
        )
    
    except Exception as e:
        return ToolResponse(
            content=[TextBlock(
                type="text",
                text=json.dumps({
                    "status": "error",
                    "error_code": "GENERATION_ERROR",
                    "message": f"Failed to generate security cases: {str(e)}"
                }, ensure_ascii=False)
            )]
        )


def apply_business_rules(testcases_json: str, rules_json: str) -> ToolResponse:
    """
    Apply business rules to test cases, updating assertions and expected values.
    
    Injects business-specific validation rules into test cases.
    For example: "Rate cannot be lower than 2.0%" or "Discount applies when use_coupon=20".
    
    Args:
        testcases_json: JSON string of test cases list
        rules_json: JSON string of business rules list. Each rule:
            - condition: Condition expression (e.g., "use_coupon == 20")
            - assertion: Assertion to add when condition is met
                - type: Assertion type
                - actual_path: JSON path to value
                - expected: Expected value
                - operator: Comparison operator
            - description: Rule description
    
    Returns:
        ToolResponse containing updated test cases:
        {
            "status": "success",
            "testcases": [...],
            "rules_applied": 5
        }
    
    Example:
        rules = [
            {
                "condition": "use_coupon == 20",
                "assertion": {
                    "type": "json_path",
                    "actual_path": "$.rate",
                    "expected": 2.0,
                    "operator": "gte"
                },
                "description": "Rate floor 2.0% when using coupon"
            }
        ]
    """
    try:
        testcases = json.loads(testcases_json) if isinstance(testcases_json, str) else testcases_json
        rules = json.loads(rules_json) if isinstance(rules_json, str) else rules_json
        
        if not testcases:
            return ToolResponse(
                content=[TextBlock(
                    type="text",
                    text=json.dumps({
                        "status": "warning",
                        "message": "No test cases provided",
                        "testcases": [],
                        "rules_applied": 0
                    }, ensure_ascii=False)
                )]
            )
        
        if not rules:
            return ToolResponse(
                content=[TextBlock(
                    type="text",
                    text=json.dumps({
                        "status": "success",
                        "message": "No rules to apply",
                        "testcases": testcases,
                        "rules_applied": 0
                    }, ensure_ascii=False)
                )]
            )
        
        rules_applied = 0
        updated_testcases = []
        
        for testcase in testcases:
            body = testcase.get("request", {}).get("body", {})
            assertions = testcase.get("assertions", [])
            
            for rule in rules:
                condition = rule.get("condition", "")
                rule_assertion = rule.get("assertion", {})
                rule_desc = rule.get("description", "")
                
                # 评估条件
                if _evaluate_condition(condition, body):
                    # 添加业务规则断言
                    new_assertion = {
                        "type": rule_assertion.get("type", "json_path"),
                        "actual_path": rule_assertion.get("actual_path"),
                        "expected": rule_assertion.get("expected"),
                        "operator": rule_assertion.get("operator", "eq"),
                        "description": f"Business rule: {rule_desc}"
                    }
                    assertions.append(new_assertion)
                    rules_applied += 1
                    
                    # 更新描述
                    if testcase.get("description"):
                        testcase["description"] += f" | Rule applied: {rule_desc}"
                    
                    # 添加标签
                    if "tags" in testcase:
                        if "business_rule" not in testcase["tags"]:
                            testcase["tags"].append("business_rule")
            
            testcase["assertions"] = assertions
            updated_testcases.append(testcase)
        
        return ToolResponse(
            content=[TextBlock(
                type="text",
                text=json.dumps({
                    "status": "success",
                    "testcases": updated_testcases,
                    "count": len(updated_testcases),
                    "rules_applied": rules_applied
                }, ensure_ascii=False)
            )]
        )
    
    except Exception as e:
        return ToolResponse(
            content=[TextBlock(
                type="text",
                text=json.dumps({
                    "status": "error",
                    "error_code": "RULE_APPLICATION_ERROR",
                    "message": f"Failed to apply business rules: {str(e)}"
                }, ensure_ascii=False)
            )]
        )


# ============= 辅助函数 =============

def _create_testcase(
    interface_name: str,
    interface_path: str,
    method: str,
    body: Dict[str, Any],
    description: str = "",
    tags: List[str] = None,
    assertions: List[Dict] = None
) -> Dict[str, Any]:
    """创建测试用例字典"""
    return {
        "id": str(uuid.uuid4()),
        "interface_name": interface_name,
        "interface_path": interface_path,
        "request": {
            "method": method,
            "url": interface_path,
            "body": body
        },
        "assertions": assertions or [
            {"type": "status_code", "expected": 200, "operator": "eq"}
        ],
        "priority": "medium",
        "tags": tags or [],
        "description": description
    }


def _get_default_value(param_type: str) -> Any:
    """根据类型获取默认值"""
    defaults = {
        "string": "test_value",
        "integer": 1,
        "number": 1.0,
        "boolean": True,
        "array": [],
        "object": {}
    }
    return defaults.get(param_type, "")


def _get_invalid_type_values(expected_type: str) -> List[tuple]:
    """获取与期望类型不匹配的无效值"""
    invalid_values = {
        "string": [
            (12345, "integer instead of string"),
            (True, "boolean instead of string"),
            (["array"], "array instead of string")
        ],
        "integer": [
            ("not_a_number", "string instead of integer"),
            (3.14, "float instead of integer"),
            (True, "boolean instead of integer")
        ],
        "number": [
            ("not_a_number", "string instead of number"),
            (True, "boolean instead of number"),
            (["array"], "array instead of number")
        ],
        "boolean": [
            ("true", "string instead of boolean"),
            (1, "integer instead of boolean"),
            ("yes", "string 'yes' instead of boolean")
        ]
    }
    return invalid_values.get(expected_type, [])


def _smart_sample(combinations: List[tuple], max_count: int) -> List[tuple]:
    """智能采样：保留边界值组合 + 均匀采样"""
    if len(combinations) <= max_count:
        return combinations
    
    # 保留首尾（边界值）
    result = [combinations[0], combinations[-1]]
    
    # 均匀采样中间值
    step = len(combinations) // (max_count - 2)
    for i in range(step, len(combinations) - step, step):
        if len(result) >= max_count:
            break
        result.append(combinations[i])
    
    return result


def _evaluate_condition(condition: str, params: Dict[str, Any]) -> bool:
    """
    安全地评估条件表达式
    
    支持简单的比较操作：
    - param == value
    - param != value
    - param > value
    - param < value
    - param in [value1, value2]
    """
    if not condition:
        return False
    
    try:
        # 解析简单条件
        # 支持格式: "param_name == value" 或 "param_name != value"
        
        # 等于判断
        if "==" in condition:
            parts = condition.split("==")
            if len(parts) == 2:
                param_name = parts[0].strip()
                expected = parts[1].strip().strip("'\"")
                actual = params.get(param_name)
                
                # 尝试类型转换
                try:
                    if expected.isdigit():
                        expected = int(expected)
                    elif expected.replace(".", "").isdigit():
                        expected = float(expected)
                except:
                    pass
                
                return actual == expected
        
        # 不等于判断
        elif "!=" in condition:
            parts = condition.split("!=")
            if len(parts) == 2:
                param_name = parts[0].strip()
                expected = parts[1].strip().strip("'\"")
                actual = params.get(param_name)
                return actual != expected
        
        # 大于判断
        elif ">" in condition and ">=" not in condition:
            parts = condition.split(">")
            if len(parts) == 2:
                param_name = parts[0].strip()
                expected = float(parts[1].strip())
                actual = params.get(param_name)
                return float(actual) > expected if actual is not None else False
        
        # 小于判断
        elif "<" in condition and "<=" not in condition:
            parts = condition.split("<")
            if len(parts) == 2:
                param_name = parts[0].strip()
                expected = float(parts[1].strip())
                actual = params.get(param_name)
                return float(actual) < expected if actual is not None else False
        
        return False
    
    except Exception:
        return False
