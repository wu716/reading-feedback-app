import os
from typing import Optional

class ProductionConfig:
    """生产环境配置 - 完全安全的 API Key 管理"""
    
    def __init__(self):
        self.environment = os.getenv("ENVIRONMENT", "development")
    
    def get_deepseek_api_key(self) -> Optional[str]:
        """获取 DeepSeek API Key - 生产环境安全版本"""
        
        if self.environment == "production":
            # 生产环境：只从云服务获取
            return self._get_from_cloud_secrets()
        else:
            # 开发环境：从环境变量获取
            return self._get_from_env()
    
    def _get_from_cloud_secrets(self) -> Optional[str]:
        """从云服务密钥管理获取（Google Secret Manager）"""
        try:
            # Google Cloud Secret Manager
            from google.cloud import secretmanager
            
            client = secretmanager.SecretManagerServiceClient()
            project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
            secret_name = f"projects/{project_id}/secrets/deepseek-api-key/versions/latest"
            
            response = client.access_secret_version(request={"name": secret_name})
            return response.payload.data.decode("UTF-8")
            
        except ImportError:
            print("⚠️  生产环境需要安装 google-cloud-secret-manager")
            return None
        except Exception as e:
            print(f"❌ 从云服务获取密钥失败: {e}")
            return None
    
    def _get_from_env(self) -> Optional[str]:
        """从环境变量获取（开发环境）"""
        api_key = os.getenv("DEEPSEEK_API_KEY")
        if not api_key:
            print("⚠️  开发环境未设置 DEEPSEEK_API_KEY 环境变量")
            print("请设置: $env:DEEPSEEK_API_KEY='your-key'")
        return api_key

# 全局配置实例
production_config = ProductionConfig()

