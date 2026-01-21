"""
配置管理模块

支持 TOML 格式配置文件的加载、验证和优先级处理。
配置加载优先级：命令行参数 > 环境变量 > 用户配置文件 > 默认配置文件
"""

import os
import toml
from pathlib import Path
from typing import Any, Dict, Optional
from pydantic import BaseModel, ValidationError


class ConfigError(Exception):
    """配置错误异常"""
    pass


class BaseConfig(BaseModel):
    """配置基类，使用 Pydantic 进行验证"""
    
    class Config:
        # 允许额外字段
        extra = "allow"
        # 使用字段别名
        populate_by_name = True


class AgentConfig(BaseConfig):
    """Agent 核心配置"""
    name: str = "MCP API Test Agent"
    version: str = "1.0.0"
    workdir: str = "./workspace"
    
    class MCPServerConfig(BaseModel):
        id: str
        command: str
        args: Optional[list[str]] = None  # 支持将命令和参数分开
        transport: str = "stdio"
        health_check_url: Optional[str] = None
        restart_policy: str = "on-failure"
    
    class MemoryConfig(BaseModel):
        short_term_capacity: int = 50
        long_term_backend: str = "chromadb"
    
    class TaskConfig(BaseModel):
        checkpoint_interval: int = 60
        checkpoint_on_item: bool = True
        retry_on_failure: bool = True
        max_retries: int = 3
    
    mcp_servers: list[MCPServerConfig] = []
    memory: MemoryConfig = MemoryConfig()
    task: TaskConfig = TaskConfig()


class DifyConfig(BaseConfig):
    """Dify API 配置"""
    api_endpoint: str = "https://your-dify-instance.com/v1/workflows/run"
    api_key: str = "your-api-key-here"
    timeout: int = 120
    max_context_tokens: int = 20000
    
    class RetryConfig(BaseModel):
        enabled: bool = True
        max_attempts: int = 3
        backoff_factor: int = 2
    
    retry: RetryConfig = RetryConfig()


class StorageConfig(BaseConfig):
    """存储配置"""
    root_path: str = "./storage"
    database_path: str = "./storage/tasks.db"
    max_task_retention_days: int = 90
    auto_cleanup: bool = True


class VectorDBConfig(BaseConfig):
    """向量数据库配置"""
    backend: str = "chromadb"
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    collection_name: str = "mcp_api_test_knowledge"
    persist_directory: str = "./storage/vectordb"
    
    class RetrievalConfig(BaseModel):
        top_k: int = 10
        similarity_threshold: float = 0.7
        token_budget: int = 5000
    
    class UpdateConfig(BaseModel):
        batch_size: int = 50
        async_update: bool = True
    
    retrieval: RetrievalConfig = RetrievalConfig()
    update: UpdateConfig = UpdateConfig()


class TestEngineConfig(BaseConfig):
    """测试引擎配置"""
    default_engine: str = "requests"
    timeout: int = 30
    max_parallel: int = 20
    retry_on_failure: bool = True
    max_retries: int = 3
    
    class ProtocolAdapterConfig(BaseModel):
        adapter_class: Optional[str] = None
        adapter_config: Dict[str, Any] = {}
    
    protocol_adapter: Optional[ProtocolAdapterConfig] = None


class WebConfig(BaseConfig):
    """前端服务配置"""
    host: str = "0.0.0.0"
    port: int = 8080
    static_path: str = "./frontend/dist"
    cors_origins: list[str] = ["*"]
    websocket_enabled: bool = True


class ModelConfig(BaseConfig):
    """模型配置"""
    model_name: str = "qwen-max"
    api_key: str = ""
    stream: bool = True
    enable_thinking: bool = True


class DefaultConfig(BaseConfig):
    """全局默认配置"""
    workdir: str = "."
    log_level: str = "INFO"
    log_file: str = "./logs/app.log"
    database_path: str = "./storage/tasks.db"


class ConfigManager:
    """配置管理器"""
    
    def __init__(self, config_dir: str = "config"):
        """
        初始化配置管理器
        
        Args:
            config_dir: 配置文件目录
        """
        self.config_dir = Path(config_dir)
        self._configs: Dict[str, BaseConfig] = {}
        self._raw_configs: Dict[str, Dict[str, Any]] = {}
    
    def load_config(self, config_name: str, config_class: type[BaseConfig],
                   override_path: Optional[str] = None) -> BaseConfig:
        """
        加载配置文件
        
        Args:
            config_name: 配置文件名（不含扩展名）
            config_class: 配置类
            override_path: 可选的覆盖配置路径
            
        Returns:
            配置对象
            
        Raises:
            ConfigError: 配置加载或验证失败
        """
        # 构建配置文件路径
        if override_path:
            config_path = Path(override_path)
        else:
            config_path = self.config_dir / f"{config_name}.toml"
        
        # 检查配置文件是否存在
        if not config_path.exists():
            # 尝试加载示例配置
            example_path = self.config_dir / f"{config_name}.toml.example"
            if example_path.exists():
                raise ConfigError(
                    f"配置文件 {config_path} 不存在，请从 {example_path} 复制并修改"
                )
            else:
                # 使用默认配置
                try:
                    config = config_class()
                    self._configs[config_name] = config
                    return config
                except ValidationError as e:
                    raise ConfigError(f"使用默认配置失败: {e}")
        
        # 加载 TOML 配置文件
        try:
            raw_config = toml.load(config_path)
            self._raw_configs[config_name] = raw_config
        except Exception as e:
            raise ConfigError(f"加载配置文件 {config_path} 失败: {e}")
        
        # 从环境变量覆盖配置
        self._apply_env_overrides(config_name, raw_config)
        
        # 验证并创建配置对象
        try:
            # 检查是否有同名的section
            if config_name in raw_config and isinstance(raw_config[config_name], dict):
                config_data = raw_config[config_name]
            else:
                config_data = raw_config
            
            config = config_class(**config_data)
            self._configs[config_name] = config
            return config
        except ValidationError as e:
            raise ConfigError(f"配置验证失败 {config_path}: {e}")
    
    def _apply_env_overrides(self, config_name: str, config_dict: Dict[str, Any]):
        """
        从环境变量覆盖配置
        
        环境变量格式：MCP_{CONFIG_NAME}_{KEY}
        例如：MCP_DIFY_API_KEY
        
        Args:
            config_name: 配置名称
            config_dict: 配置字典（会被原地修改）
        """
        prefix = f"MCP_{config_name.upper()}_"
        
        for env_key, env_value in os.environ.items():
            if env_key.startswith(prefix):
                # 提取配置键
                config_key = env_key[len(prefix):].lower()
                # 支持嵌套键，如 memory_short_term_capacity
                keys = config_key.split('_')
                
                # 递归设置嵌套值
                current = config_dict
                for i, key in enumerate(keys[:-1]):
                    if key not in current:
                        current[key] = {}
                    current = current[key]
                
                # 设置最终值（尝试类型转换）
                final_key = keys[-1]
                current[final_key] = self._convert_env_value(env_value)
    
    def _convert_env_value(self, value: str) -> Any:
        """
        转换环境变量值的类型
        
        Args:
            value: 环境变量字符串值
            
        Returns:
            转换后的值
        """
        # 布尔值
        if value.lower() in ('true', 'yes', '1'):
            return True
        if value.lower() in ('false', 'no', '0'):
            return False
        
        # 整数
        try:
            return int(value)
        except ValueError:
            pass
        
        # 浮点数
        try:
            return float(value)
        except ValueError:
            pass
        
        # 字符串
        return value
    
    def get_config(self, config_name: str) -> Optional[BaseConfig]:
        """
        获取已加载的配置
        
        Args:
            config_name: 配置名称
            
        Returns:
            配置对象，如果未加载则返回 None
        """
        return self._configs.get(config_name)
    
    def get_raw_config(self, config_name: str) -> Optional[Dict[str, Any]]:
        """
        获取原始配置字典
        
        Args:
            config_name: 配置名称
            
        Returns:
            原始配置字典，如果未加载则返回 None
        """
        return self._raw_configs.get(config_name)
    
    def reload_config(self, config_name: str) -> BaseConfig:
        """
        重新加载配置
        
        Args:
            config_name: 配置名称
            
        Returns:
            重新加载的配置对象
            
        Raises:
            ConfigError: 配置重载失败
        """
        if config_name not in self._configs:
            raise ConfigError(f"配置 {config_name} 未加载")
        
        config_class = type(self._configs[config_name])
        return self.load_config(config_name, config_class)
    
    def save_config(self, config_name: str, config: BaseConfig):
        """
        保存配置到文件
        
        Args:
            config_name: 配置名称
            config: 配置对象
            
        Raises:
            ConfigError: 配置保存失败
        """
        config_path = self.config_dir / f"{config_name}.toml"
        
        try:
            # 转换为字典
            config_dict = config.dict()
            
            # 保存到文件
            with open(config_path, 'w', encoding='utf-8') as f:
                toml.dump(config_dict, f)
            
            # 更新缓存
            self._configs[config_name] = config
            self._raw_configs[config_name] = config_dict
        except Exception as e:
            raise ConfigError(f"保存配置文件 {config_path} 失败: {e}")
    
    def validate_all_configs(self) -> Dict[str, Optional[str]]:
        """
        验证所有已加载的配置
        
        Returns:
            验证结果字典，键为配置名称，值为错误信息（None 表示验证通过）
        """
        results = {}
        
        for config_name, config in self._configs.items():
            try:
                # Pydantic 模型已在加载时验证
                # 这里可以添加额外的业务逻辑验证
                results[config_name] = None
            except Exception as e:
                results[config_name] = str(e)
        
        return results


# 全局配置管理器实例
_config_manager: Optional[ConfigManager] = None


def get_config_manager(config_dir: str = "config") -> ConfigManager:
    """
    获取全局配置管理器实例（单例模式）
    
    Args:
        config_dir: 配置文件目录
        
    Returns:
        配置管理器实例
    """
    global _config_manager
    if _config_manager is None:
        _config_manager = ConfigManager(config_dir)
    return _config_manager


def load_all_configs(config_dir: str = "config") -> Dict[str, BaseConfig]:
    """
    加载所有标准配置文件
    
    Args:
        config_dir: 配置文件目录
        
    Returns:
        配置字典
    """
    manager = get_config_manager(config_dir)
    
    configs = {}
    
    # 定义配置文件和对应的类
    config_mapping = {
        'default': DefaultConfig,
        'agent': AgentConfig,
        'dify': DifyConfig,
        'storage': StorageConfig,
        'vectordb': VectorDBConfig,
        'testengine': TestEngineConfig,
        'web': WebConfig,
        'model': ModelConfig,
    }
    
    # 加载所有配置
    for config_name, config_class in config_mapping.items():
        try:
            configs[config_name] = manager.load_config(config_name, config_class)
        except ConfigError as e:
            # 配置加载失败时记录错误但继续加载其他配置
            print(f"警告: 加载配置 {config_name} 失败: {e}")
            # 使用默认配置
            configs[config_name] = config_class()
    
    return configs
