# -*- coding: utf-8 -*-
"""
数据库操作工具集

提供数据库连接、表结构查询、SQL 执行等功能，
用于分支测试中的测试数据准备和验证。

支持的数据库：MySQL、PostgreSQL、Oracle（通过 JDBC 或 Python 驱动）
"""

import json
from typing import Any, Dict, List, Optional
from enum import Enum
from agentscope.tool import ToolResponse
from agentscope.message import TextBlock


class DatabaseType(str, Enum):
    """支持的数据库类型"""
    MYSQL = "mysql"
    POSTGRESQL = "postgresql"
    ORACLE = "oracle"
    H2 = "h2"


# 连接池缓存（简化实现）
_connection_pool: Dict[str, Any] = {}


def connect_database(
    connection_string: str,
    db_type: str = "mysql",
    timeout: int = 30
) -> ToolResponse:
    """
    建立数据库连接
    
    建立到测试数据库的连接，返回连接标识用于后续操作。
    连接会被缓存，可通过相同 connection_string 复用。
    
    Args:
        connection_string: 数据库连接字符串
          - MySQL: "mysql://user:password@host:port/database?charset=utf8"
          - PostgreSQL: "postgresql://user:password@host:port/database"
          - Oracle: "oracle://user:password@host:port/SID"
          - H2 (内存): "h2:mem:testdb;DB_CLOSE_DELAY=-1"
        db_type: 数据库类型，默认 "mysql"
        timeout: 连接超时（秒），默认 30
    
    Returns:
        ToolResponse containing connection info:
        {
            "status": "success",
            "connection_id": "conn_abc123",
            "db_type": "mysql",
            "database": "loan_test",
            "server_version": "8.0.32",
            "connected_at": "2024-01-15T10:30:00Z",
            "warning": "TEST ENVIRONMENT ONLY - Never connect to production"
        }
    
    Example:
        # 连接 MySQL 测试库
        connect_database(
            "mysql://test_user:test_pass@localhost:3306/loan_test?charset=utf8",
            db_type="mysql"
        )
        
        # 连接 H2 内存数据库（快速测试）
        connect_database(
            "h2:mem:testdb;DB_CLOSE_DELAY=-1",
            db_type="h2"
        )
    """
    try:
        # 安全警告：确保不是生产环境
        if any(keyword in connection_string.lower() for keyword in 
               ["prod", "production", "live", "prd"]):
            return ToolResponse(
                content=[TextBlock(
                    type="text",
                    text=json.dumps({
                        "status": "error",
                        "error_code": "PRODUCTION_BLOCKED",
                        "message": "Connection to production database is not allowed. Use test environment only."
                    }, ensure_ascii=False)
                )]
            )
        
        # 生成连接ID
        import hashlib
        conn_id = f"conn_{hashlib.md5(connection_string.encode()).hexdigest()[:8]}"
        
        # 模拟建立连接（实际实现会创建真实连接）
        db_info = _parse_connection_string(connection_string, db_type)
        
        # 缓存连接信息
        _connection_pool[conn_id] = {
            "connection_string": connection_string,
            "db_type": db_type,
            "database": db_info.get("database", "unknown"),
            "connected_at": "2024-01-15T10:30:00Z"
        }
        
        return ToolResponse(
            content=[TextBlock(
                type="text",
                text=json.dumps({
                    "status": "success",
                    "connection_id": conn_id,
                    "db_type": db_type,
                    "database": db_info.get("database", "unknown"),
                    "server_version": "8.0.32",
                    "connected_at": "2024-01-15T10:30:00Z",
                    "warning": "TEST ENVIRONMENT ONLY - Never connect to production"
                }, ensure_ascii=False)
            )]
        )
    
    except Exception as e:
        return ToolResponse(
            content=[TextBlock(
                type="text",
                text=json.dumps({
                    "status": "error",
                    "error_code": "CONNECTION_FAILED",
                    "message": f"Failed to connect database: {str(e)}"
                }, ensure_ascii=False)
            )]
        )


def query_table_structure(
    table_name: str,
    connection_id: str = "",
    include_constraints: bool = True
) -> ToolResponse:
    """
    查询表结构信息
    
    获取指定表的字段定义、类型、约束等信息，用于生成测试 SQL。
    
    Args:
        table_name: 表名，如 "LOAN_APPLICATION", "T_LOAN_INFO"
        connection_id: 连接标识（由 connect_database 返回），
                      空字符串时使用默认连接
        include_constraints: 是否包含约束信息（主键、外键、索引），默认 True
    
    Returns:
        ToolResponse containing table structure:
        {
            "status": "success",
            "table_name": "LOAN_APPLICATION",
            "columns": [
                {
                    "name": "LOAN_ID",
                    "type": "VARCHAR(32)",
                    "nullable": false,
                    "default": null,
                    "comment": "贷款申请编号",
                    "is_primary_key": true
                },
                {
                    "name": "AMOUNT",
                    "type": "DECIMAL(18,2)",
                    "nullable": false,
                    "default": "0.00",
                    "comment": "贷款金额"
                },
                {
                    "name": "STATUS",
                    "type": "VARCHAR(20)",
                    "nullable": false,
                    "default": "PENDING",
                    "comment": "申请状态",
                    "enum_values": ["PENDING", "PENDING_REVIEW", "AUTO_APPROVED", "REJECTED"]
                }
            ],
            "primary_key": ["LOAN_ID"],
            "foreign_keys": [
                {
                    "column": "CUSTOMER_ID",
                    "ref_table": "CUSTOMER_INFO",
                    "ref_column": "CUSTOMER_ID"
                }
            ],
            "indexes": [
                {"name": "IDX_LOAN_STATUS", "columns": ["STATUS"], "unique": false}
            ]
        }
    
    Example:
        # 查询贷款申请表结构
        query_table_structure("LOAN_APPLICATION", connection_id="conn_abc123")
        
        # 只查询字段信息（不包含约束）
        query_table_structure("LOAN_APPLICATION", include_constraints=False)
    """
    try:
        # 检查连接
        if connection_id and connection_id not in _connection_pool:
            return ToolResponse(
                content=[TextBlock(
                    type="text",
                    text=json.dumps({
                        "status": "error",
                        "error_code": "INVALID_CONNECTION",
                        "message": f"Connection {connection_id} not found. Call connect_database first."
                    }, ensure_ascii=False)
                )]
            )
        
        # 模拟表结构（实际实现会查询 INFORMATION_SCHEMA）
        mock_structure = _mock_table_structure(table_name, include_constraints)
        
        return ToolResponse(
            content=[TextBlock(
                type="text",
                text=json.dumps({
                    "status": "success",
                    "table_name": table_name,
                    **mock_structure
                }, ensure_ascii=False)
            )]
        )
    
    except Exception as e:
        return ToolResponse(
            content=[TextBlock(
                type="text",
                text=json.dumps({
                    "status": "error",
                    "error_code": "QUERY_FAILED",
                    "message": f"Failed to query table structure: {str(e)}"
                }, ensure_ascii=False)
            )]
        )


def execute_sql(
    sql: str,
    connection_id: str = "",
    operation_type: str = "query",
    expect_affected_rows: int = -1
) -> ToolResponse:
    """
    执行 SQL 语句
    
    执行 DML（SELECT/INSERT/UPDATE/DELETE）或 DDL 语句。
    用于测试数据准备（INSERT）和清理（DELETE）。
    
    Args:
        sql: SQL 语句
        connection_id: 连接标识，空字符串时使用默认连接
        operation_type: 操作类型，用于结果验证
                       - "query": 查询，返回结果集
                       - "insert": 插入，返回生成的主键
                       - "update": 更新，返回影响行数
                       - "delete": 删除，返回影响行数
        expect_affected_rows: 期望的影响行数，-1 表示不验证
                             验证失败时返回警告但不报错
    
    Returns:
        ToolResponse containing execution result:
        
        查询 (query):
        {
            "status": "success",
            "operation": "query",
            "row_count": 3,
            "columns": ["LOAN_ID", "AMOUNT", "STATUS"],
            "rows": [
                {"LOAN_ID": "TEST001", "AMOUNT": 1500000.00, "STATUS": "PENDING"}
            ]
        }
        
        插入 (insert):
        {
            "status": "success",
            "operation": "insert",
            "affected_rows": 1,
            "generated_keys": {"LOAN_ID": "TEST001"},
            "execution_time_ms": 45
        }
        
        删除 (delete):
        {
            "status": "success",
            "operation": "delete",
            "affected_rows": 1,
            "execution_time_ms": 23,
            "warning": "Expected 2 rows but affected 1"
        }
    
    Example:
        # 查询测试数据
        execute_sql(
            "SELECT * FROM LOAN_APPLICATION WHERE LOAN_ID = 'TEST001'",
            operation_type="query"
        )
        
        # 插入测试数据
        execute_sql(
            "INSERT INTO LOAN_APPLICATION (LOAN_ID, AMOUNT, STATUS) VALUES ('TEST001', 1500000, 'PENDING')",
            operation_type="insert"
        )
        
        # 清理测试数据
        execute_sql(
            "DELETE FROM LOAN_APPLICATION WHERE LOAN_ID = 'TEST001'",
            operation_type="delete",
            expect_affected_rows=1
        )
        
        # 批量删除（注意 WHERE 条件，防止误删）
        execute_sql(
            "DELETE FROM LOAN_APPLICATION WHERE LOAN_ID LIKE 'TEST%'",
            operation_type="delete"
        )
    """
    try:
        # 安全检查：禁止危险操作
        upper_sql = sql.upper().strip()
        
        # 禁止无 WHERE 的 UPDATE/DELETE
        if (upper_sql.startswith("UPDATE") or upper_sql.startswith("DELETE")) \
           and "WHERE" not in upper_sql:
            return ToolResponse(
                content=[TextBlock(
                    type="text",
                    text=json.dumps({
                        "status": "error",
                        "error_code": "UNSAFE_OPERATION",
                        "message": "UPDATE/DELETE without WHERE clause is not allowed. Add WHERE condition to limit affected rows."
                    }, ensure_ascii=False)
                )]
            )
        
        # 禁止 DROP/TRUNCATE 等破坏性操作
        dangerous_keywords = ["DROP ", "TRUNCATE ", "ALTER ", "GRANT ", "REVOKE "]
        if any(keyword in upper_sql for keyword in dangerous_keywords):
            return ToolResponse(
                content=[TextBlock(
                    type="text",
                    text=json.dumps({
                        "status": "error",
                        "error_code": "DANGEROUS_OPERATION",
                        "message": "DROP/TRUNCATE/ALTER/GRANT operations are not allowed in test environment."
                    }, ensure_ascii=False)
                )]
            )
        
        # 模拟执行（实际实现会使用真实连接）
        mock_result = _mock_execute_sql(sql, operation_type, expect_affected_rows)
        
        return ToolResponse(
            content=[TextBlock(
                type="text",
                text=json.dumps({
                    "status": "success",
                    "sql": sql[:100] + "..." if len(sql) > 100 else sql,
                    **mock_result
                }, ensure_ascii=False)
            )]
        )
    
    except Exception as e:
        return ToolResponse(
            content=[TextBlock(
                type="text",
                text=json.dumps({
                    "status": "error",
                    "error_code": "EXECUTION_FAILED",
                    "message": f"SQL execution failed: {str(e)}"
                }, ensure_ascii=False)
            )]
        )


# ==================== 辅助函数 ====================

def _parse_connection_string(connection_string: str, db_type: str) -> Dict:
    """解析连接字符串获取基本信息"""
    # 简化解析，实际实现会使用 URI 解析器
    if "://" in connection_string:
        # 格式: type://user:pass@host:port/database
        parts = connection_string.split("://")[1].split("/")
        database = parts[1].split("?")[0] if len(parts) > 1 else "unknown"
    elif ":" in connection_string:
        # H2 格式: h2:mem:database
        database = connection_string.split(":")[-1].split(";")[0]
    else:
        database = "unknown"
    
    return {"database": database, "type": db_type}


def _mock_table_structure(table_name: str, include_constraints: bool) -> Dict:
    """模拟表结构"""
    columns = [
        {
            "name": "LOAN_ID",
            "type": "VARCHAR(32)",
            "nullable": False,
            "default": None,
            "comment": "贷款申请编号",
            "is_primary_key": True
        },
        {
            "name": "CUSTOMER_ID",
            "type": "VARCHAR(32)",
            "nullable": False,
            "default": None,
            "comment": "客户编号"
        },
        {
            "name": "AMOUNT",
            "type": "DECIMAL(18,2)",
            "nullable": False,
            "default": "0.00",
            "comment": "贷款金额"
        },
        {
            "name": "LOAN_TYPE",
            "type": "VARCHAR(20)",
            "nullable": False,
            "default": None,
            "comment": "贷款类型",
            "enum_values": ["PERSONAL", "ENTERPRISE", "MORTGAGE"]
        },
        {
            "name": "STATUS",
            "type": "VARCHAR(20)",
            "nullable": False,
            "default": "PENDING",
            "comment": "申请状态",
            "enum_values": ["PENDING", "PENDING_REVIEW", "AUTO_APPROVED", "REJECTED"]
        },
        {
            "name": "CREATE_TIME",
            "type": "TIMESTAMP",
            "nullable": False,
            "default": "CURRENT_TIMESTAMP",
            "comment": "创建时间"
        }
    ]
    
    result = {"columns": columns}
    
    if include_constraints:
        result["primary_key"] = ["LOAN_ID"]
        result["foreign_keys"] = [
            {
                "column": "CUSTOMER_ID",
                "ref_table": "CUSTOMER_INFO",
                "ref_column": "CUSTOMER_ID"
            }
        ]
        result["indexes"] = [
            {"name": "IDX_LOAN_STATUS", "columns": ["STATUS"], "unique": False},
            {"name": "IDX_LOAN_CUSTOMER", "columns": ["CUSTOMER_ID"], "unique": False}
        ]
    
    return result


def _mock_execute_sql(sql: str, operation_type: str, expect_affected_rows: int) -> Dict:
    """模拟 SQL 执行结果"""
    import re
    
    upper_sql = sql.upper().strip()
    
    if operation_type == "query" or upper_sql.startswith("SELECT"):
        # 模拟查询结果
        return {
            "operation": "query",
            "row_count": 1,
            "columns": ["LOAN_ID", "AMOUNT", "STATUS"],
            "rows": [
                {"LOAN_ID": "TEST001", "AMOUNT": 1500000.00, "STATUS": "PENDING_REVIEW"}
            ],
            "execution_time_ms": 15
        }
    
    elif operation_type == "insert" or upper_sql.startswith("INSERT"):
        # 提取 LOAN_ID
        loan_id_match = re.search(r"'?(TEST\d+)'?", sql)
        loan_id = loan_id_match.group(1) if loan_id_match else "TEST001"
        
        return {
            "operation": "insert",
            "affected_rows": 1,
            "generated_keys": {"LOAN_ID": loan_id},
            "execution_time_ms": 45
        }
    
    elif operation_type == "delete" or upper_sql.startswith("DELETE"):
        affected = 1 if "TEST" in sql else 0
        
        result = {
            "operation": "delete",
            "affected_rows": affected,
            "execution_time_ms": 23
        }
        
        # 验证影响行数
        if expect_affected_rows >= 0 and affected != expect_affected_rows:
            result["warning"] = f"Expected {expect_affected_rows} rows but affected {affected}"
        
        return result
    
    elif operation_type == "update" or upper_sql.startswith("UPDATE"):
        return {
            "operation": "update",
            "affected_rows": 1,
            "execution_time_ms": 30
        }
    
    else:
        return {
            "operation": "unknown",
            "message": "Operation completed"
        }
