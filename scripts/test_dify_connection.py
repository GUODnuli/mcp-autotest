"""
Dify API 连接测试脚本

用于验证 Dify API 配置是否正确
"""

import requests
import json
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from backend.common.config import load_all_configs


def test_dify_connection():
    """测试 Dify API 连接"""
    
    print("=" * 60)
    print("Dify API 连接测试")
    print("=" * 60)
    
    # 加载配置文件
    try:
        print("\n1. 加载配置文件...")
        configs = load_all_configs()
        dify_config = configs["dify"]
        
        api_endpoint = dify_config.api_endpoint
        api_key = dify_config.api_key
        timeout = dify_config.timeout
        
        print(f"   ✅ 配置加载成功")
        print(f"   API 端点: {api_endpoint}")
        print(f"   API Key: {api_key[:15]}..." if len(api_key) > 15 else f"   API Key: {api_key}")
        print(f"   超时时间: {timeout}s")
        
    except Exception as e:
        print(f"   ❌ 配置加载失败: {str(e)}")
        print("\n请确保 config/dify.toml 文件存在并配置正确")
        return
    
    # 构建测试请求
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "inputs": {
            "system_prompt": "你是一个测试助手",
            "user_query": "你好，请回复'连接成功'"
        },
        "response_mode": "blocking",
        "user": "test_user"
    }
    
    print(f"\n2. 发送测试请求...")
    
    try:
        response = requests.post(
            api_endpoint,
            headers=headers,
            json=payload,
            timeout=timeout
        )
        
        print(f"\n3. 响应状态码: {response.status_code}")
        
        if response.status_code == 200:
            print("✅ 连接成功！")
            print(f"\n响应内容:")
            print(json.dumps(response.json(), indent=2, ensure_ascii=False))
        else:
            print(f"❌ 请求失败")
            print(f"响应内容: {response.text}")
            
    except requests.exceptions.ConnectionError as e:
        print(f"\n❌ 连接错误: {str(e)}")
        print("\n可能的原因:")
        print("  1. API 端点 URL 不正确")
        print("  2. Dify 服务未启动或不可访问")
        print("  3. 网络/防火墙阻止连接")
        
    except requests.exceptions.Timeout:
        print(f"\n❌ 请求超时")
        print("Dify 服务响应太慢或不可用")
        
    except Exception as e:
        print(f"\n❌ 未知错误: {str(e)}")
    
    print("\n" + "=" * 60)


if __name__ == "__main__":
    test_dify_connection()
