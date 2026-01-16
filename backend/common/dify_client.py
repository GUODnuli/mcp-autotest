"""
Dify API 客户端

提供与 Dify 工作流 API 的交互接口。
"""

import requests
import time
from typing import Any, Dict, Optional

from ..common.logger import get_logger


class DifyAPIError(Exception):
    """Dify API 异常"""
    pass


class DifyClient:
    """Dify API 客户端"""
    
    def __init__(self, config: Dict[str, Any]):
        """
        初始化 Dify 客户端
        
        Args:
            config: Dify 配置（来自 dify.toml）
        """
        self.api_endpoint = config.get("api_endpoint")
        self.api_key = config.get("api_key")
        self.timeout = config.get("timeout", 120)
        self.max_context_tokens = config.get("max_context_tokens", 20000)
        
        # 重试配置
        retry_config = config.get("retry", {})
        self.retry_enabled = retry_config.get("enabled", True)
        self.max_attempts = retry_config.get("max_attempts", 3)
        self.backoff_factor = retry_config.get("backoff_factor", 2)
        
        self.logger = get_logger()
        
        if not self.api_endpoint or not self.api_key:
            raise DifyAPIError("Dify API 配置不完整，请检查 api_endpoint 和 api_key")
        
        self.logger.info(f"Dify 客户端初始化 | endpoint: {self.api_endpoint}")
    
    def call_workflow(
        self,
        inputs: Dict[str, Any],
        user: str = "mcp-agent"
    ) -> Dict[str, Any]:
        """
        调用 Dify 工作流
        
        Args:
            inputs: 工作流输入参数
            user: 用户标识
            
        Returns:
            工作流输出结果
            
        Raises:
            DifyAPIError: API 调用失败
        """
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "inputs": inputs,
            "response_mode": "blocking",
            "user": user
        }
        
        attempt = 0
        last_error = None
        
        while attempt < self.max_attempts:
            try:
                self.logger.info(
                    f"调用 Dify API | 尝试: {attempt + 1}/{self.max_attempts}"
                )
                
                response = requests.post(
                    self.api_endpoint,
                    headers=headers,
                    json=payload,
                    timeout=self.timeout
                )
                
                # 检查响应状态
                if response.status_code == 200:
                    result = response.json()
                    
                    # 支持多种响应格式
                    # 格式1: {"data": {"outputs": {...}}} - 标准工作流
                    # 格式2: {"text": "..."} - 文本生成工作流
                    if "data" in result and "outputs" in result["data"]:
                        outputs = result["data"]["outputs"]
                        self.logger.info("Dify API 调用成功")
                        return {"data": {"outputs": outputs}}
                    elif "text" in result:
                        # 文本生成工作流，包装为标准格式
                        self.logger.info("Dify API 调用成功（文本格式）")
                        return {"data": {"outputs": {"text": result["text"]}}}
                    else:
                        self.logger.warning(f"Dify API 响应格式异常: {result}")
                        return {"data": {"outputs": result}}
                
                elif response.status_code == 429:  # Rate limit
                    wait_time = self.backoff_factor ** attempt
                    self.logger.warning(
                        f"Dify API 速率限制 | 等待 {wait_time} 秒后重试"
                    )
                    time.sleep(wait_time)
                    attempt += 1
                    continue
                
                else:
                    error_msg = f"Dify API 返回错误 | 状态码: {response.status_code} | 响应: {response.text}"
                    self.logger.error(error_msg)
                    raise DifyAPIError(error_msg)
            
            except requests.Timeout:
                last_error = "请求超时"
                self.logger.warning(f"Dify API 请求超时 | 尝试: {attempt + 1}")
                attempt += 1
                if attempt < self.max_attempts:
                    time.sleep(self.backoff_factor ** attempt)
            
            except requests.RequestException as e:
                last_error = str(e)
                self.logger.error(f"Dify API 请求异常: {e}")
                attempt += 1
                if attempt < self.max_attempts and self.retry_enabled:
                    time.sleep(self.backoff_factor ** attempt)
                else:
                    break
        
        # 所有重试都失败
        raise DifyAPIError(f"Dify API 调用失败（已重试 {attempt} 次）: {last_error}")
    
    def estimate_tokens(self, text: str) -> int:
        """
        估算文本的 token 数量
        
        使用简单的估算方法：英文约 4 字符/token，中文约 1.5 字符/token
        
        Args:
            text: 文本内容
            
        Returns:
            估算的 token 数量
        """
        # 简单估算：统计中英文字符
        chinese_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
        english_chars = len(text) - chinese_chars
        
        # 中文约 1.5 字符/token，英文约 4 字符/token
        estimated_tokens = int(chinese_chars / 1.5 + english_chars / 4)
        
        return estimated_tokens
    
    def check_context_size(self, text: str) -> bool:
        """
        检查文本是否超过上下文限制
        
        Args:
            text: 文本内容
            
        Returns:
            是否在限制内
        """
        tokens = self.estimate_tokens(text)
        return tokens <= self.max_context_tokens
