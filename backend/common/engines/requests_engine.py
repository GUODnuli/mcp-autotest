"""
Requests 测试引擎

基于 requests 库实现的轻量级 HTTP 测试引擎。
支持基本的 HTTP 请求执行和断言验证。
"""

import time
import re
import json
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode

import requests
from jsonpath_ng import parse as jsonpath_parse

from backend.common.test_models import (
    TestEngine,
    TestCase,
    TestResult,
    Response,
    Assertion,
    AssertionResult,
    AssertionType,
    AssertionOperator,
    TestCaseStatus
)
from backend.common.logger import Logger


class RequestsEngine(TestEngine):
    """
    基于 requests 库的测试引擎
    
    特性：
    - 支持 GET/POST/PUT/DELETE/PATCH 等 HTTP 方法
    - 支持请求重试机制
    - 支持多种断言类型（状态码、JSON Path、正则、包含等）
    - 支持请求超时控制
    - 详细的日志追踪（符合用户调试偏好：DEBUG < INFO）
    """
    
    def __init__(self):
        self.logger: Optional[Logger] = None
        self.session: Optional[requests.Session] = None
        self.config: Dict[str, Any] = {}
        self.initialized = False
    
    def initialize(self, config: Dict[str, Any]):
        """
        初始化引擎配置
        
        Args:
            config: 引擎配置，支持的键：
                - log_level: 日志级别（DEBUG/INFO/WARNING/ERROR）
                - max_retries: 最大重试次数（默认 3）
                - retry_delay: 重试延迟（秒，默认 1）
                - verify_ssl: 是否验证 SSL 证书（默认 True）
                - default_timeout: 默认超时时间（秒，默认 30）
        """
        self.config = config
        
        # 初始化日志系统
        log_level = config.get("log_level", "INFO")
        self.logger = Logger(log_level=log_level, enable_file=False)
        
        # 创建 requests session
        self.session = requests.Session()
        
        # 配置重试机制
        max_retries = config.get("max_retries", 3)
        retry_adapter = requests.adapters.HTTPAdapter(max_retries=max_retries)
        self.session.mount("http://", retry_adapter)
        self.session.mount("https://", retry_adapter)
        
        # 配置 SSL 验证
        self.session.verify = config.get("verify_ssl", True)
        
        self.initialized = True
        
        self.logger.info(
            f"RequestsEngine 初始化成功 | "
            f"日志级别: {log_level} (提醒：DEBUG < INFO < WARNING < ERROR) | "
            f"最大重试: {max_retries} | "
            f"SSL验证: {self.session.verify}",
            engine="RequestsEngine"
        )
    
    def execute_testcase(self, testcase: TestCase) -> TestResult:
        """
        执行单个测试用例
        
        Args:
            testcase: 测试用例对象
            
        Returns:
            测试结果对象
        """
        if not self.initialized:
            raise RuntimeError("引擎未初始化，请先调用 initialize()")
        
        start_time = time.time()
        test_result = TestResult(
            testcase_id=testcase.id,
            interface_name=testcase.interface_name,
            status=TestCaseStatus.RUNNING,
            duration=0.0,
            request_log={}
        )
        
        try:
            self.logger.info(
                f"开始执行测试用例 | "
                f"用例ID: {testcase.id} | "
                f"接口: {testcase.interface_name} | "
                f"方法: {testcase.request.method} | "
                f"URL: {testcase.request.url}",
                testcase_id=testcase.id,
                interface=testcase.interface_name
            )
            
            # 发送 HTTP 请求
            response = self._send_request(testcase)
            
            # 记录请求详情
            test_result.request_log = {
                "method": testcase.request.method,
                "url": testcase.request.url,
                "headers": testcase.request.headers or {},
                "query_params": testcase.request.query_params or {},
                "body": testcase.request.body
            }
            
            # 记录响应详情
            test_result.response_log = {
                "status_code": response.status_code,
                "headers": dict(response.headers),
                "body": response.body,
                "elapsed": response.elapsed,
                "timestamp": response.timestamp
            }
            
            # 执行断言验证
            assertion_results = self.validate_assertions(response, testcase.assertions)
            test_result.assertion_results = assertion_results
            
            # 判断测试结果
            all_passed = all(ar.passed for ar in assertion_results)
            test_result.status = TestCaseStatus.PASSED if all_passed else TestCaseStatus.FAILED
            
            if not all_passed:
                failed_assertions = [ar for ar in assertion_results if not ar.passed]
                test_result.error_message = f"有 {len(failed_assertions)} 个断言失败"
                
                self.logger.warning(
                    f"测试用例执行失败 | "
                    f"用例ID: {testcase.id} | "
                    f"失败断言数: {len(failed_assertions)}",
                    testcase_id=testcase.id,
                    status="FAILED"
                )
            else:
                self.logger.info(
                    f"测试用例执行成功 | "
                    f"用例ID: {testcase.id} | "
                    f"所有断言通过",
                    testcase_id=testcase.id,
                    status="PASSED"
                )
        
        except requests.exceptions.Timeout as e:
            test_result.status = TestCaseStatus.ERROR
            test_result.error_message = f"请求超时: {str(e)}"
            self.logger.error(
                f"测试用例执行超时 | 用例ID: {testcase.id} | 错误: {str(e)}",
                testcase_id=testcase.id,
                error=str(e)
            )
        
        except requests.exceptions.ConnectionError as e:
            test_result.status = TestCaseStatus.ERROR
            test_result.error_message = f"连接错误: {str(e)}"
            self.logger.error(
                f"测试用例连接失败 | 用例ID: {testcase.id} | 错误: {str(e)}",
                testcase_id=testcase.id,
                error=str(e)
            )
        
        except Exception as e:
            test_result.status = TestCaseStatus.ERROR
            test_result.error_message = f"未知错误: {str(e)}"
            self.logger.error(
                f"测试用例执行异常 | 用例ID: {testcase.id} | 错误: {str(e)}",
                testcase_id=testcase.id,
                error=str(e),
                exc_info=True
            )
        
        finally:
            test_result.duration = time.time() - start_time
        
        return test_result
    
    def _send_request(self, testcase: TestCase) -> Response:
        """
        发送 HTTP 请求
        
        Args:
            testcase: 测试用例
            
        Returns:
            响应对象
        """
        request = testcase.request
        
        # 构建完整 URL（含查询参数）
        url = request.url
        if request.query_params:
            url = f"{url}?{urlencode(request.query_params)}"
        
        # 准备请求参数
        req_kwargs = {
            "method": request.method.upper(),
            "url": url,
            "headers": request.headers or {},
            "timeout": request.timeout or self.config.get("default_timeout", 30)
        }
        
        # 处理请求体
        if request.body:
            if isinstance(request.body, dict):
                # 自动设置 Content-Type
                if "Content-Type" not in req_kwargs["headers"]:
                    req_kwargs["headers"]["Content-Type"] = "application/json"
                req_kwargs["json"] = request.body
            else:
                req_kwargs["data"] = request.body
        
        # 打印完整的请求信息（避免 loguru 格式化冲突）
        try:
            import json
            request_info = {
                "method": req_kwargs["method"],
                "url": url,
                "headers": req_kwargs["headers"],
                "body": request.body,
                "query_params": request.query_params or {}
            }
            request_str = json.dumps(request_info, ensure_ascii=False, indent=2)
            log_msg = "发送 HTTP 请求 | 用例ID: " + str(testcase.id) + " | 请求详情:\n" + request_str
            from loguru import logger
            logger.opt(raw=True).info(log_msg + "\n")
        except Exception as e:
            self.logger.warning(f"请求日志打印失败: {str(e)}")
        
        # 发送请求
        start_time = time.time()
        raw_response = self.session.request(**req_kwargs)
        elapsed = time.time() - start_time
        
        # 解析响应体
        try:
            if "application/json" in raw_response.headers.get("Content-Type", ""):
                body = raw_response.json()
            else:
                body = raw_response.text
        except Exception:
            body = raw_response.content
        
        # 构建 Response 对象
        response = Response(
            status_code=raw_response.status_code,
            headers=dict(raw_response.headers),
            body=body,
            elapsed=elapsed
        )
        
        # 打印响应信息
        try:
            response_info = {
                "status_code": response.status_code,
                "elapsed": f"{elapsed:.3f}s",
                "body": body if isinstance(body, (dict, list)) else str(body)[:200]
            }
            response_str = json.dumps(response_info, ensure_ascii=False, indent=2)
            log_msg = "收到 HTTP 响应 | 用例ID: " + str(testcase.id) + " | 响应详情:\n" + response_str
            logger.opt(raw=True).info(log_msg + "\n")
        except Exception as e:
            self.logger.warning(f"响应日志打印失败: {str(e)}")
        
        return response
    
    def validate_assertions(
        self,
        response: Response,
        assertions: List[Assertion]
    ) -> List[AssertionResult]:
        """
        执行断言验证
        
        Args:
            response: HTTP 响应对象
            assertions: 断言规则列表
            
        Returns:
            断言结果列表
        """
        results = []
        
        for assertion in assertions:
            result = self._validate_single_assertion(response, assertion)
            results.append(result)
            
            if result.passed:
                self.logger.debug(
                    f"断言通过 | "
                    f"类型: {assertion.type} | "
                    f"期望: {assertion.expected} | "
                    f"实际: {result.actual_value}",
                    assertion_type=assertion.type,
                    passed=True
                )
            else:
                self.logger.warning(
                    f"断言失败 | "
                    f"类型: {assertion.type} | "
                    f"期望: {assertion.expected} | "
                    f"实际: {result.actual_value} | "
                    f"错误: {result.error_message}",
                    assertion_type=assertion.type,
                    passed=False
                )
        
        return results
    
    def _validate_single_assertion(
        self,
        response: Response,
        assertion: Assertion
    ) -> AssertionResult:
        """
        验证单个断言
        
        Args:
            response: HTTP 响应
            assertion: 断言规则
            
        Returns:
            断言结果
        """
        try:
            if assertion.type == AssertionType.STATUS_CODE:
                return self._validate_status_code(response, assertion)
            
            elif assertion.type == AssertionType.JSON_PATH:
                return self._validate_json_path(response, assertion)
            
            elif assertion.type == AssertionType.REGEX:
                return self._validate_regex(response, assertion)
            
            elif assertion.type == AssertionType.CONTAINS:
                return self._validate_contains(response, assertion)
            
            elif assertion.type == AssertionType.EQUALS:
                return self._validate_equals(response, assertion)
            
            elif assertion.type == AssertionType.NOT_EQUALS:
                return self._validate_not_equals(response, assertion)
            
            elif assertion.type == AssertionType.GREATER_THAN:
                return self._validate_greater_than(response, assertion)
            
            elif assertion.type == AssertionType.LESS_THAN:
                return self._validate_less_than(response, assertion)
            
            else:
                return AssertionResult(
                    assertion=assertion,
                    passed=False,
                    error_message=f"不支持的断言类型: {assertion.type}"
                )
        
        except Exception as e:
            return AssertionResult(
                assertion=assertion,
                passed=False,
                error_message=f"断言执行异常: {str(e)}"
            )
    
    def _validate_status_code(
        self,
        response: Response,
        assertion: Assertion
    ) -> AssertionResult:
        """验证 HTTP 状态码"""
        actual = response.status_code
        expected = assertion.expected
        passed = self._compare_values(actual, expected, assertion.operator)
        
        return AssertionResult(
            assertion=assertion,
            passed=passed,
            actual_value=actual,
            error_message=None if passed else f"状态码不匹配: 期望 {expected}, 实际 {actual}"
        )
    
    def _validate_json_path(
        self,
        response: Response,
        assertion: Assertion
    ) -> AssertionResult:
        """验证 JSON Path 表达式"""
        if not isinstance(response.body, dict):
            return AssertionResult(
                assertion=assertion,
                passed=False,
                error_message="响应体不是 JSON 格式"
            )
        
        if not assertion.actual_path:
            return AssertionResult(
                assertion=assertion,
                passed=False,
                error_message="缺少 JSON Path 表达式"
            )
        
        try:
            # 解析 JSON Path
            jsonpath_expr = jsonpath_parse(assertion.actual_path)
            matches = [match.value for match in jsonpath_expr.find(response.body)]
            
            if not matches:
                return AssertionResult(
                    assertion=assertion,
                    passed=False,
                    actual_value=None,
                    error_message=f"JSON Path 未找到匹配: {assertion.actual_path}"
                )
            
            # 取第一个匹配值
            actual = matches[0]
            expected = assertion.expected
            passed = self._compare_values(actual, expected, assertion.operator)
            
            return AssertionResult(
                assertion=assertion,
                passed=passed,
                actual_value=actual,
                error_message=None if passed else f"值不匹配: 期望 {expected}, 实际 {actual}"
            )
        
        except Exception as e:
            return AssertionResult(
                assertion=assertion,
                passed=False,
                error_message=f"JSON Path 解析失败: {str(e)}"
            )
    
    def _validate_regex(
        self,
        response: Response,
        assertion: Assertion
    ) -> AssertionResult:
        """验证正则表达式"""
        # 转换响应体为字符串
        if isinstance(response.body, bytes):
            body_str = response.body.decode("utf-8", errors="ignore")
        elif isinstance(response.body, dict):
            body_str = json.dumps(response.body)
        else:
            body_str = str(response.body)
        
        try:
            pattern = str(assertion.expected)
            matches = re.search(pattern, body_str)
            passed = matches is not None
            
            return AssertionResult(
                assertion=assertion,
                passed=passed,
                actual_value=matches.group(0) if matches else None,
                error_message=None if passed else f"正则表达式未匹配: {pattern}"
            )
        
        except Exception as e:
            return AssertionResult(
                assertion=assertion,
                passed=False,
                error_message=f"正则表达式错误: {str(e)}"
            )
    
    def _validate_contains(
        self,
        response: Response,
        assertion: Assertion
    ) -> AssertionResult:
        """验证包含关系"""
        # 提取实际值
        if assertion.actual_path:
            # 使用 JSON Path 提取
            if not isinstance(response.body, dict):
                return AssertionResult(
                    assertion=assertion,
                    passed=False,
                    error_message="响应体不是 JSON 格式"
                )
            
            try:
                jsonpath_expr = jsonpath_parse(assertion.actual_path)
                matches = [match.value for match in jsonpath_expr.find(response.body)]
                actual = matches[0] if matches else None
            except Exception as e:
                return AssertionResult(
                    assertion=assertion,
                    passed=False,
                    error_message=f"JSON Path 解析失败: {str(e)}"
                )
        else:
            # 使用整个响应体
            actual = response.body
        
        expected = assertion.expected
        
        # 执行包含检查
        try:
            if isinstance(actual, (list, tuple)):
                passed = expected in actual
            elif isinstance(actual, dict):
                passed = expected in actual.values()
            elif isinstance(actual, str):
                passed = str(expected) in actual
            else:
                passed = False
            
            return AssertionResult(
                assertion=assertion,
                passed=passed,
                actual_value=actual,
                error_message=None if passed else f"不包含期望值: {expected}"
            )
        
        except Exception as e:
            return AssertionResult(
                assertion=assertion,
                passed=False,
                error_message=f"包含检查失败: {str(e)}"
            )
    
    def _validate_equals(
        self,
        response: Response,
        assertion: Assertion
    ) -> AssertionResult:
        """验证相等性"""
        actual = self._extract_value(response, assertion.actual_path)
        expected = assertion.expected
        passed = actual == expected
        
        return AssertionResult(
            assertion=assertion,
            passed=passed,
            actual_value=actual,
            error_message=None if passed else f"值不相等: 期望 {expected}, 实际 {actual}"
        )
    
    def _validate_not_equals(
        self,
        response: Response,
        assertion: Assertion
    ) -> AssertionResult:
        """验证不相等"""
        actual = self._extract_value(response, assertion.actual_path)
        expected = assertion.expected
        passed = actual != expected
        
        return AssertionResult(
            assertion=assertion,
            passed=passed,
            actual_value=actual,
            error_message=None if passed else f"值相等: {actual}"
        )
    
    def _validate_greater_than(
        self,
        response: Response,
        assertion: Assertion
    ) -> AssertionResult:
        """验证大于关系"""
        actual = self._extract_value(response, assertion.actual_path)
        expected = assertion.expected
        
        try:
            passed = float(actual) > float(expected)
            return AssertionResult(
                assertion=assertion,
                passed=passed,
                actual_value=actual,
                error_message=None if passed else f"不满足大于关系: {actual} <= {expected}"
            )
        except (ValueError, TypeError) as e:
            return AssertionResult(
                assertion=assertion,
                passed=False,
                error_message=f"无法比较数值: {str(e)}"
            )
    
    def _validate_less_than(
        self,
        response: Response,
        assertion: Assertion
    ) -> AssertionResult:
        """验证小于关系"""
        actual = self._extract_value(response, assertion.actual_path)
        expected = assertion.expected
        
        try:
            passed = float(actual) < float(expected)
            return AssertionResult(
                assertion=assertion,
                passed=passed,
                actual_value=actual,
                error_message=None if passed else f"不满足小于关系: {actual} >= {expected}"
            )
        except (ValueError, TypeError) as e:
            return AssertionResult(
                assertion=assertion,
                passed=False,
                error_message=f"无法比较数值: {str(e)}"
            )
    
    def _extract_value(
        self,
        response: Response,
        path: Optional[str]
    ) -> Any:
        """
        从响应中提取值
        
        Args:
            response: HTTP 响应
            path: JSON Path 表达式（可选）
            
        Returns:
            提取的值
        """
        if not path:
            return response.body
        
        if not isinstance(response.body, dict):
            raise ValueError("响应体不是 JSON 格式")
        
        try:
            jsonpath_expr = jsonpath_parse(path)
            matches = [match.value for match in jsonpath_expr.find(response.body)]
            return matches[0] if matches else None
        except Exception as e:
            raise ValueError(f"JSON Path 解析失败: {str(e)}")
    
    def _compare_values(
        self,
        actual: Any,
        expected: Any,
        operator: AssertionOperator
    ) -> bool:
        """
        比较两个值
        
        Args:
            actual: 实际值
            expected: 期望值
            operator: 比较运算符
            
        Returns:
            比较结果
        """
        try:
            if operator == AssertionOperator.EQ:
                return actual == expected
            elif operator == AssertionOperator.NE:
                return actual != expected
            elif operator == AssertionOperator.GT:
                return float(actual) > float(expected)
            elif operator == AssertionOperator.LT:
                return float(actual) < float(expected)
            elif operator == AssertionOperator.GTE:
                return float(actual) >= float(expected)
            elif operator == AssertionOperator.LTE:
                return float(actual) <= float(expected)
            elif operator == AssertionOperator.IN:
                return expected in actual
            elif operator == AssertionOperator.NOT_IN:
                return expected not in actual
            else:
                raise ValueError(f"不支持的运算符: {operator}")
        except Exception:
            return False
    
    def cleanup(self):
        """清理资源"""
        if self.session:
            self.session.close()
            self.session = None
        
        if self.logger:
            self.logger.info("RequestsEngine 资源已清理", engine="RequestsEngine")
        
        self.initialized = False
