import os
import sys
from pathlib import Path

# 确保项目根目录在 Python 路径中
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from backend.common.config import get_config_manager, load_all_configs
from backend.agent.chat_agent import AgentFactory

def test_config_loading():
    print("Testing config loading...")
    configs = load_all_configs()
    model_config = configs.get("model")
    if model_config:
        print(f"Model name: {model_config.model_name}")
        print(f"Stream: {model_config.stream}")
    else:
        print("Model config NOT found!")

def test_factory():
    print("\nTesting AgentFactory...")
    factory = AgentFactory()
    
    print("Creating chat agent...")
    chat_agent = factory.create_agent(agent_type="chat", name="ChatTest")
    print(f"Chat agent formatter: {type(chat_agent.formatter)}")
    
    print("Creating plan agent...")
    plan_agent = factory.create_agent(agent_type="plan", name="PlanTest")
    print(f"Plan agent formatter: {type(plan_agent.formatter)}")
    
    print("Creating exe agent...")
    exe_agent = factory.create_agent(agent_type="exe", name="ExeTest")
    print(f"Exe agent formatter: {type(exe_agent.formatter)}")

if __name__ == "__main__":
    # 模拟配置文件
    model_toml = project_root / "config" / "model.toml"
    if not model_toml.exists():
        with open(model_toml, "w") as f:
            f.write('[model]\nmodel_name = "qwen-max"\napi_key = "test-key"\nstream = true\n')
    
    try:
        test_config_loading()
        test_factory()
    finally:
        # 清理临时配置文件（如果之前不存在）
        # if model_toml.exists():
        #     os.remove(model_toml)
        pass
