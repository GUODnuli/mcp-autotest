# -*- coding: utf-8 -*-
"""
代码索引查询工具集

基于预构建的代码索引（符号表、调用图、注解索引）进行查询，
支持 Coordinator-Workers 架构下的代码分析需求。

注意：这些工具依赖外部代码索引服务（如 tree-sitter 构建的索引），
实际执行由 Coordinator 路由到对应的 Index Service。
"""

import json
from typing import Any, Dict, List, Optional
from agentscope.tool import ToolResponse
from agentscope.message import TextBlock


def search_symbol(
    pattern: str,
    symbol_type: str = "",
    language: str = "java",
    limit: int = 20
) -> ToolResponse:
    """
    搜索代码符号（类、方法、字段等）
    
    基于预构建的符号索引进行模糊或精确匹配搜索。
    支持通配符：* 匹配任意字符，? 匹配单个字符
    
    Args:
        pattern: 搜索模式，如 "LoanController", "*apply*", "Loan*Service"
        symbol_type: 符号类型过滤，可选 "CLASS", "METHOD", "FIELD", "INTERFACE", "ENUM"
                      空字符串表示不过滤
        language: 编程语言，默认 "java"
        limit: 返回结果数量上限，默认 20
    
    Returns:
        ToolResponse containing search results:
        {
            "status": "success",
            "query": {"pattern": "...", "type": "..."},
            "results": [
                {
                    "fqn": "com.bank.loan.controller.LoanController",
                    "name": "LoanController",
                    "type": "CLASS",
                    "file": "src/main/java/com/bank/loan/controller/LoanController.java",
                    "line": 15,
                    "signature": "public class LoanController",
                    "score": 0.95
                }
            ],
            "total": 1
        }
    
    Example:
        # 搜索包含 "apply" 的方法
        search_symbol("*apply*", symbol_type="METHOD")
        
        # 精确搜索类名
        search_symbol("LoanController", symbol_type="CLASS")
        
        # 模糊搜索服务类
        search_symbol("*Loan*Service", symbol_type="CLASS", limit=10)
    """
    try:
        # 构建查询请求
        query = {
            "pattern": pattern,
            "symbol_type": symbol_type,
            "language": language,
            "limit": limit
        }
        
        # 模拟调用索引服务（实际由 Coordinator 路由到 Index Service）
        # 这里返回模拟数据，展示期望的格式
        mock_results = _mock_search_symbol(pattern, symbol_type, limit)
        
        return ToolResponse(
            content=[TextBlock(
                type="text",
                text=json.dumps({
                    "status": "success",
                    "query": query,
                    "results": mock_results,
                    "total": len(mock_results),
                    "note": "Results are from pre-built symbol index"
                }, ensure_ascii=False)
            )]
        )
    
    except Exception as e:
        return ToolResponse(
            content=[TextBlock(
                type="text",
                text=json.dumps({
                    "status": "error",
                    "error_code": "SEARCH_FAILED",
                    "message": f"Symbol search failed: {str(e)}"
                }, ensure_ascii=False)
            )]
        )


def get_call_chain(
    fqn: str,
    direction: str = "downstream",
    depth: int = 5,
    include_external: bool = False
) -> ToolResponse:
    """
    获取方法调用链
    
    基于预构建的调用图（call graph）查询指定方法的上游或下游调用关系。
    
    Args:
        fqn: 方法的完全限定名，如 "com.bank.loan.controller.LoanController.apply"
        direction: 查询方向，"downstream"（被谁调用）或 "upstream"（调用谁）
        depth: 查询深度，默认 5 层
        include_external: 是否包含外部服务调用（如 SOA 服务），默认 False
    
    Returns:
        ToolResponse containing call chain:
        {
            "status": "success",
            "entry_point": "com.bank.loan.controller.LoanController.apply",
            "direction": "downstream",
            "chain": [
                {
                    "depth": 0,
                    "fqn": "com.bank.loan.controller.LoanController.apply",
                    "layer": "UCC",
                    "calls": [
                        {
                            "target": "com.bank.loan.service.LoanService.submitApplication",
                            "type": "internal",
                            "line": 48
                        }
                    ]
                },
                {
                    "depth": 1,
                    "fqn": "com.bank.loan.service.LoanService.submitApplication",
                    "layer": "BS",
                    "calls": [
                        {
                            "target": "com.bank.loan.mapper.LoanMapper.insertApplication",
                            "type": "internal",
                            "line": 72
                        },
                        {
                            "target": "com.bank.credit.CreditService.queryReport",
                            "type": "external",
                            "protocol": "SOAP",
                            "service_id": "credit-service"
                        }
                    ]
                },
                {
                    "depth": 2,
                    "fqn": "com.bank.loan.mapper.LoanMapper.insertApplication",
                    "layer": "DAO",
                    "sql_id": "insertApplication"
                }
            ],
            "external_calls": [
                {
                    "fqn": "com.bank.credit.CreditService.queryReport",
                    "protocol": "SOAP",
                    "service_id": "credit-service"
                }
            ]
        }
    
    Example:
        # 获取入口方法的下游调用链（UCC -> BS -> DAO）
        get_call_chain(
            "com.bank.loan.controller.LoanController.apply",
            direction="downstream",
            depth=5
        )
        
        # 获取方法的上游调用（谁调用了我）
        get_call_chain(
            "com.bank.loan.mapper.LoanMapper.insertApplication",
            direction="upstream",
            depth=3
        )
    """
    try:
        query = {
            "fqn": fqn,
            "direction": direction,
            "depth": depth,
            "include_external": include_external
        }
        
        # 模拟调用调用图服务
        mock_chain = _mock_call_chain(fqn, direction, depth, include_external)
        
        return ToolResponse(
            content=[TextBlock(
                type="text",
                text=json.dumps({
                    "status": "success",
                    "query": query,
                    "entry_point": fqn,
                    **mock_chain
                }, ensure_ascii=False)
            )]
        )
    
    except Exception as e:
        return ToolResponse(
            content=[TextBlock(
                type="text",
                text=json.dumps({
                    "status": "error",
                    "error_code": "CALL_CHAIN_FAILED",
                    "message": f"Call chain query failed: {str(e)}"
                }, ensure_ascii=False)
            )]
        )


def find_by_annotation(
    annotation: str,
    value: str = "",
    scope: str = "METHOD",
    codebase_path: str = ""
) -> ToolResponse:
    """
    通过注解查找代码元素
    
    基于预构建的注解索引，查找带有指定注解的类、方法或字段。
    常用于定位 Spring 事务入口（如 @TransCode, @RequestMapping）。
    
    Args:
        annotation: 注解名称，如 "TransCode", "RequestMapping", "Service"
                   可带或不带 @ 前缀
        value: 注解属性值过滤，如 "LN_LOAN_APPLY"
               空字符串表示不过滤属性值
        scope: 查找范围，"CLASS", "METHOD", "FIELD"，默认 "METHOD"
        codebase_path: 代码库路径（可选，用于多代码库场景）
    
    Returns:
        ToolResponse containing annotation matches:
        {
            "status": "success",
            "annotation": "@TransCode",
            "value_filter": "LN_LOAN_APPLY",
            "matches": [
                {
                    "fqn": "com.bank.loan.controller.LoanController.apply",
                    "type": "METHOD",
                    "file": "src/main/java/com/bank/loan/controller/LoanController.java",
                    "line": 45,
                    "annotation_params": {
                        "value": "LN_LOAN_APPLY",
                        "name": "Loan Apply",
                        "version": "v1"
                    },
                    "method_signature": "public Response apply(LoanRequest request)"
                }
            ],
            "total": 1
        }
    
    Example:
        # 查找 @TransCode("LN_LOAN_APPLY") 标注的方法
        find_by_annotation("TransCode", value="LN_LOAN_APPLY", scope="METHOD")
        
        # 查找所有 @Service 标注的类
        find_by_annotation("Service", scope="CLASS")
        
        # 查找 @RequestMapping("/api/loan") 的方法
        find_by_annotation("RequestMapping", value="/api/loan")
    """
    try:
        # 标准化注解名称
        annotation = annotation if annotation.startswith("@") else f"@{annotation}"
        
        query = {
            "annotation": annotation,
            "value": value,
            "scope": scope,
            "codebase_path": codebase_path
        }
        
        # 模拟调用注解索引服务
        mock_matches = _mock_find_by_annotation(annotation, value, scope)
        
        return ToolResponse(
            content=[TextBlock(
                type="text",
                text=json.dumps({
                    "status": "success",
                    "query": query,
                    "annotation": annotation,
                    "value_filter": value,
                    "matches": mock_matches,
                    "total": len(mock_matches)
                }, ensure_ascii=False)
            )]
        )
    
    except Exception as e:
        return ToolResponse(
            content=[TextBlock(
                type="text",
                text=json.dumps({
                    "status": "error",
                    "error_code": "ANNOTATION_SEARCH_FAILED",
                    "message": f"Annotation search failed: {str(e)}"
                }, ensure_ascii=False)
            )]
        )


def read_method_source(
    fqn: str,
    include_body: bool = True,
    max_tokens: int = 2000
) -> ToolResponse:
    """
    读取方法源代码
    
    从代码库中读取指定方法的完整源代码，用于分支逻辑分析。
    
    Args:
        fqn: 方法的完全限定名
        include_body: 是否包含方法体，默认 True
                      False 时只返回方法签名和注释
        max_tokens: 最大返回 token 数，默认 2000（防止超大方法）
    
    Returns:
        ToolResponse containing method source:
        {
            "status": "success",
            "fqn": "com.bank.loan.service.LoanService.submitApplication",
            "file": "src/main/java/com/bank/loan/service/LoanService.java",
            "line_range": [45, 89],
            "signature": "public Response submitApplication(LoanRequest request)",
            "annotations": ["@Transactional"],
            "source": "public Response submitApplication(LoanRequest request) {\n    // ...",
            "byte_size": 1240,
            "truncated": false
        }
    
    Example:
        # 读取完整方法源码用于分支分析
        read_method_source(
            "com.bank.loan.service.LoanService.submitApplication",
            include_body=True
        )
        
        # 只读取方法签名（轻量）
        read_method_source(
            "com.bank.loan.mapper.LoanMapper.insertApplication",
            include_body=False
        )
    """
    try:
        query = {
            "fqn": fqn,
            "include_body": include_body,
            "max_tokens": max_tokens
        }
        
        # 模拟读取源码
        mock_source = _mock_read_method_source(fqn, include_body, max_tokens)
        
        return ToolResponse(
            content=[TextBlock(
                type="text",
                text=json.dumps({
                    "status": "success",
                    "query": query,
                    **mock_source
                }, ensure_ascii=False)
            )]
        )
    
    except Exception as e:
        return ToolResponse(
            content=[TextBlock(
                type="text",
                text=json.dumps({
                    "status": "error",
                    "error_code": "SOURCE_READ_FAILED",
                    "message": f"Failed to read method source: {str(e)}"
                }, ensure_ascii=False)
            )]
        )


# ==================== Mock 实现（实际由 Index Service 提供） ====================

def _mock_search_symbol(pattern: str, symbol_type: str, limit: int) -> List[Dict]:
    """模拟符号搜索结果"""
    results = []
    
    if "Controller" in pattern or symbol_type == "CLASS":
        results.append({
            "fqn": "com.bank.loan.controller.LoanController",
            "name": "LoanController",
            "type": "CLASS",
            "file": "src/main/java/com/bank/loan/controller/LoanController.java",
            "line": 15,
            "signature": "public class LoanController",
            "score": 0.95
        })
    
    if "apply" in pattern.lower() or symbol_type == "METHOD":
        results.append({
            "fqn": "com.bank.loan.controller.LoanController.apply",
            "name": "apply",
            "type": "METHOD",
            "file": "src/main/java/com/bank/loan/controller/LoanController.java",
            "line": 45,
            "signature": "public Response apply(LoanRequest request)",
            "score": 0.92
        })
    
    return results[:limit]


def _mock_call_chain(fqn: str, direction: str, depth: int, include_external: bool) -> Dict:
    """模拟调用链结果"""
    chain = []
    external_calls = []
    
    if "Controller" in fqn and direction == "downstream":
        chain = [
            {
                "depth": 0,
                "fqn": fqn,
                "layer": "UCC",
                "calls": [
                    {
                        "target": "com.bank.loan.service.LoanService.submitApplication",
                        "type": "internal",
                        "line": 48
                    }
                ]
            },
            {
                "depth": 1,
                "fqn": "com.bank.loan.service.LoanService.submitApplication",
                "layer": "BS",
                "calls": [
                    {
                        "target": "com.bank.loan.mapper.LoanMapper.insertApplication",
                        "type": "internal",
                        "line": 72
                    }
                ]
            },
            {
                "depth": 2,
                "fqn": "com.bank.loan.mapper.LoanMapper.insertApplication",
                "layer": "DAO",
                "sql_id": "insertApplication"
            }
        ]
        
        if include_external:
            chain[1]["calls"].append({
                "target": "com.bank.credit.CreditService.queryReport",
                "type": "external",
                "protocol": "SOAP",
                "service_id": "credit-service"
            })
            external_calls.append({
                "fqn": "com.bank.credit.CreditService.queryReport",
                "protocol": "SOAP",
                "service_id": "credit-service"
            })
    
    return {
        "direction": direction,
        "max_depth": depth,
        "chain": chain[:depth + 1],
        "external_calls": external_calls if include_external else []
    }


def _mock_find_by_annotation(annotation: str, value: str, scope: str) -> List[Dict]:
    """模拟注解搜索结果"""
    results = []
    
    if "TransCode" in annotation and value == "LN_LOAN_APPLY":
        results.append({
            "fqn": "com.bank.loan.controller.LoanController.apply",
            "type": "METHOD",
            "file": "src/main/java/com/bank/loan/controller/LoanController.java",
            "line": 45,
            "annotation_params": {
                "value": "LN_LOAN_APPLY",
                "name": "Loan Application",
                "version": "v1"
            },
            "method_signature": "public Response apply(LoanRequest request)"
        })
    
    if "Service" in annotation and scope == "CLASS":
        results.append({
            "fqn": "com.bank.loan.service.LoanService",
            "type": "CLASS",
            "file": "src/main/java/com/bank/loan/service/LoanService.java",
            "line": 18,
            "annotation_params": {"value": ""}
        })
    
    return results


def _mock_read_method_source(fqn: str, include_body: bool, max_tokens: int) -> Dict:
    """模拟源码读取结果"""
    signature = "public Response submitApplication(LoanRequest request)"
    annotations = ["@Transactional"]
    
    if include_body:
        source = '''@Transactional
public Response submitApplication(LoanRequest request) {
    // Validate input
    if (request.getAmount() == null || request.getAmount() <= 0) {
        throw new IllegalArgumentException("Invalid amount");
    }
    
    // Check amount threshold
    if (request.getAmount() > 1000000) {
        // Requires risk control approval
        request.setStatus("PENDING_REVIEW");
    } else {
        // Auto approval
        request.setStatus("AUTO_APPROVED");
    }
    
    // Save to database
    loanMapper.insertApplication(request);
    
    return Response.success(request);
}'''
    else:
        source = signature
    
    return {
        "fqn": fqn,
        "file": f"src/main/java/{fqn.replace('.', '/')}.java",
        "line_range": [45, 89],
        "signature": signature,
        "annotations": annotations,
        "source": source[:max_tokens] if len(source) > max_tokens else source,
        "byte_size": len(source),
        "truncated": len(source) > max_tokens
    }
