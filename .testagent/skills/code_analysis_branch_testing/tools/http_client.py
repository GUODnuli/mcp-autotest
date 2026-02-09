# -*- coding: utf-8 -*-
"""
HTTP 通信工具集

提供 HTTP 请求发送功能，用于执行接口测试。
支持 RESTful API、SOA 服务网关等多种协议。
"""

import json
import time
from typing import Any, Dict, List, Optional
from agentscope.tool import ToolResponse
from agentscope.message import TextBlock

try:
    import requests as _requests
except ImportError:
    _requests = None


def send_request(
    method: str,
    url: str,
    headers: Dict[str, str] = None,
    body: Dict[str, Any] = None,
    query_params: Dict[str, str] = None,
    timeout: int = 30,
    verify_ssl: bool = True
) -> ToolResponse:
    """
    发送 HTTP 请求
    
    发送 HTTP 请求到指定端点，用于执行接口测试。
    支持 RESTful API、SOA 网关等常见接口形式。
    
    Args:
        method: HTTP 方法，"GET", "POST", "PUT", "DELETE", "PATCH"
        url: 请求 URL，如 "http://gateway.bank.com/api/loan/apply"
        headers: 请求头，默认包含 {"Content-Type": "application/json"}
        body: 请求体（JSON 对象），用于 POST/PUT/PATCH
        query_params: URL 查询参数
        timeout: 超时时间（秒），默认 30
        verify_ssl: 是否验证 SSL 证书，默认 True
    
    Returns:
        ToolResponse containing response:
        {
            "status": "success",
            "request": {
                "method": "POST",
                "url": "http://gateway.bank.com/api/loan/apply",
                "headers": {...}
            },
            "response": {
                "status_code": 200,
                "status_text": "OK",
                "headers": {"Content-Type": "application/json"},
                "body": {"code": "SUCCESS", "data": {...}},
                "elapsed_ms": 245
            },
            "timing": {
                "dns_lookup_ms": 12,
                "connection_ms": 25,
                "ttfb_ms": 180,
                "total_ms": 245
            }
        }
    
    Example:
        # 发送贷款申请请求（带 SOA 服务ID）
        send_request(
            method="POST",
            url="http://gateway.bank.com/api/loan/apply",
            headers={
                "Content-Type": "application/json",
                "service_id": "LN_LOAN_APPLY",
                "X-Request-ID": "req-123456"
            },
            body={
                "loan_id": "TEST001",
                "amount": 1500000,
                "loan_type": "PERSONAL",
                "applicant_name": "Test User",
                "id_no": "110101199001011234"
            }
        )
        
        # 查询请求（GET + 查询参数）
        send_request(
            method="GET",
            url="http://gateway.bank.com/api/loan/query",
            headers={"service_id": "LN_LOAN_QUERY"},
            query_params={"loan_id": "TEST001"}
        )
    """
    try:
        # 准备请求信息
        request_info = {
            "method": method.upper(),
            "url": url,
            "headers": headers or {"Content-Type": "application/json"}
        }
        
        if body:
            request_info["body"] = body
        if query_params:
            request_info["query_params"] = query_params
        
        # 发送真实 HTTP 请求
        if _requests is None:
            return ToolResponse(
                content=[TextBlock(
                    type="text",
                    text=json.dumps({
                        "status": "error",
                        "error_code": "MISSING_DEPENDENCY",
                        "message": "requests library not installed. Run: pip install requests"
                    }, ensure_ascii=False)
                )]
            )

        actual_headers = headers or {"Content-Type": "application/json"}
        start_time = time.time()

        resp = _requests.request(
            method=method.upper(),
            url=url,
            headers=actual_headers,
            json=body if body and method.upper() in ("POST", "PUT", "PATCH") else None,
            params=query_params,
            timeout=timeout,
            verify=verify_ssl,
        )

        elapsed_ms = int((time.time() - start_time) * 1000)

        # 解析响应体
        try:
            response_body = resp.json()
        except (json.JSONDecodeError, ValueError):
            response_body = resp.text

        response_data = {
            "response": {
                "status_code": resp.status_code,
                "status_text": resp.reason,
                "headers": dict(resp.headers),
                "body": response_body,
                "elapsed_ms": elapsed_ms,
            },
            "timing": {
                "total_ms": elapsed_ms,
            },
        }

        return ToolResponse(
            content=[TextBlock(
                type="text",
                text=json.dumps({
                    "status": "success",
                    "request": request_info,
                    **response_data
                }, ensure_ascii=False, default=str)
            )]
        )
    
    except Exception as e:
        return ToolResponse(
            content=[TextBlock(
                type="text",
                text=json.dumps({
                    "status": "error",
                    "error_code": "REQUEST_FAILED",
                    "message": f"HTTP request failed: {str(e)}"
                }, ensure_ascii=False)
            )]
        )


def build_soa_request(
    service_id: str,
    operation: str,
    body: Dict[str, Any],
    headers: Dict[str, str] = None,
    gateway_url: str = ""
) -> ToolResponse:
    """
    构建 SOA 服务请求
    
    为 SOA 架构构建标准请求，自动添加服务标识等必要头信息。
    
    Args:
        service_id: SOA 服务ID，如 "LN_LOAN_APPLY", "CR_CREDIT_QUERY"
        operation: 操作名，如 "submitApplication", "queryReport"
        body: 业务参数
        headers: 额外请求头
        gateway_url: 网关地址，默认使用配置中的地址
    
    Returns:
        ToolResponse containing ready-to-send request config:
        {
            "status": "success",
            "request_config": {
                "method": "POST",
                "url": "http://gateway.bank.com/api/soa/invoke",
                "headers": {
                    "Content-Type": "application/json",
                    "service_id": "LN_LOAN_APPLY",
                    "operation": "submitApplication",
                    "version": "1.0"
                },
                "body": {...}
            }
        }
    
    Example:
        # 构建贷款申请 SOA 请求
        result = build_soa_request(
            service_id="LN_LOAN_APPLY",
            operation="submitApplication",
            body={
                "loan_id": "TEST001",
                "amount": 1500000,
                "loan_type": "PERSONAL"
            }
        )
        
        # 使用返回的配置发送请求
        config = result["request_config"]
        send_request(**config)
    """
    try:
        # 默认网关地址
        if not gateway_url:
            gateway_url = "http://gateway.bank.com/api/soa/invoke"
        
        # 构建 SOA 标准头
        soa_headers = {
            "Content-Type": "application/json",
            "service_id": service_id,
            "operation": operation,
            "version": "1.0"
        }
        
        # 合并额外头
        if headers:
            soa_headers.update(headers)
        
        request_config = {
            "method": "POST",
            "url": gateway_url,
            "headers": soa_headers,
            "body": body
        }
        
        return ToolResponse(
            content=[TextBlock(
                type="text",
                text=json.dumps({
                    "status": "success",
                    "service_id": service_id,
                    "operation": operation,
                    "request_config": request_config
                }, ensure_ascii=False)
            )]
        )
    
    except Exception as e:
        return ToolResponse(
            content=[TextBlock(
                type="text",
                text=json.dumps({
                    "status": "error",
                    "error_code": "BUILD_FAILED",
                    "message": f"Failed to build SOA request: {str(e)}"
                }, ensure_ascii=False)
            )]
        )


def validate_response(
    response_json: str,
    expected_status: int = 200,
    expected_fields: Dict[str, Any] = None,
    json_path_checks: Dict[str, Any] = None
) -> ToolResponse:
    """
    验证 HTTP 响应
    
    验证响应状态码、字段值等是否符合预期。
    
    Args:
        response_json: send_request 返回的响应 JSON
        expected_status: 期望的 HTTP 状态码，默认 200
        expected_fields: 期望的字段值，如 {"code": "SUCCESS", "success": true}
        json_path_checks: JSONPath 检查，如 {"$.data.status": "APPROVED"}
    
    Returns:
        ToolResponse containing validation result:
        {
            "status": "success",
            "validation": {
                "all_passed": true,
                "checks": [
                    {"check": "status_code", "expected": 200, "actual": 200, "passed": true},
                    {"check": "field:code", "expected": "SUCCESS", "actual": "SUCCESS", "passed": true},
                    {"check": "jsonpath:$.data.review_required", "expected": true, "actual": true, "passed": true}
                ]
            },
            "branch_triggered": "amount > 1000000"
        }
    
    Example:
        # 基础验证（状态码 + 返回码）
        validate_response(
            response_json=json.dumps(response),
            expected_status=200,
            expected_fields={"code": "SUCCESS"}
        )
        
        # 高级验证（JSONPath）
        validate_response(
            response_json=json.dumps(response),
            expected_fields={"code": "SUCCESS"},
            json_path_checks={
                "$.data.review_required": True,  # 验证风控分支触发
                "$.data.loan_id": "TEST001"
            }
        )
    """
    try:
        response = json.loads(response_json) if isinstance(response_json, str) else response_json
        
        checks = []
        all_passed = True
        
        # 检查状态码
        actual_status = response.get("response", {}).get("status_code", 0)
        status_passed = actual_status == expected_status
        checks.append({
            "check": "status_code",
            "expected": expected_status,
            "actual": actual_status,
            "passed": status_passed
        })
        all_passed = all_passed and status_passed
        
        # 检查字段值
        body = response.get("response", {}).get("body", {})
        if expected_fields:
            for field, expected_value in expected_fields.items():
                actual_value = body.get(field)
                field_passed = actual_value == expected_value
                checks.append({
                    "check": f"field:{field}",
                    "expected": expected_value,
                    "actual": actual_value,
                    "passed": field_passed
                })
                all_passed = all_passed and field_passed
        
        # 推断分支触发（基于验证结果）
        branch_triggered = _infer_branch_triggered(body, json_path_checks)
        
        return ToolResponse(
            content=[TextBlock(
                type="text",
                text=json.dumps({
                    "status": "success",
                    "validation": {
                        "all_passed": all_passed,
                        "checks": checks
                    },
                    "branch_triggered": branch_triggered
                }, ensure_ascii=False)
            )]
        )
    
    except Exception as e:
        return ToolResponse(
            content=[TextBlock(
                type="text",
                text=json.dumps({
                    "status": "error",
                    "error_code": "VALIDATION_FAILED",
                    "message": f"Response validation failed: {str(e)}"
                }, ensure_ascii=False)
            )]
        )


def _infer_branch_triggered(body: Dict, json_path_checks: Dict) -> str:
    """根据响应推断触发的分支"""
    data = body.get("data", {})
    
    # 检查风控分支
    if data.get("review_required"):
        return "amount > 1000000 (risk control branch)"
    
    # 检查自动审批分支
    if data.get("status") == "AUTO_APPROVED":
        return "amount <= 1000000 (auto approval branch)"
    
    return "unknown branch"
