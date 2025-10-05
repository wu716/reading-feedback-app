# 添加安全工具函数
def validate_user_access(user_id: int, current_user_id: int) -> bool:
    """验证用户是否有权访问数据"""
    return user_id == current_user_id

def enforce_user_ownership(model_instance, current_user_id: int):
    """强制用户所有权验证"""
    if hasattr(model_instance, 'user_id') and model_instance.user_id != current_user_id:
        raise HTTPException(status_code=404, detail="资源不存在")
