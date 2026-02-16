"""
Authentication and authorization module.
Provides RBAC, JWT authentication, and password hashing.
"""

from src.auth.jwt import create_access_token, decode_access_token
from src.auth.password import hash_password, verify_password
from src.auth.rbac import RBACManager

__all__ = [
    "create_access_token",
    "decode_access_token",
    "hash_password",
    "verify_password",
    "RBACManager",
]
