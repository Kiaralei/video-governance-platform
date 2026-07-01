"""JWT 认证 + RBAC。对齐设计 §7.3 / §12.1。

- 密码用 stdlib PBKDF2-SHA256 加盐哈希（不引额外依赖）。
- 令牌用 PyJWT HS256：access（短期）+ refresh（长期），claim 里带 type 区分。
- RBAC：Role 枚举 + ENDPOINT_PERMISSIONS 映射 + FastAPI 依赖 require_permission。
"""

from __future__ import annotations

import hashlib
import hmac
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum

import jwt
from fastapi import Depends, HTTPException, Request

from .config import settings


class Role(str, Enum):
    REVIEWER_T1 = "reviewer_t1"
    REVIEWER_T2 = "reviewer_t2"
    REVIEWER_T3 = "reviewer_t3"
    SENIOR_REVIEWER = "senior_reviewer"
    QA_REVIEWER = "qa_reviewer"
    APPEAL_REVIEWER = "appeal_reviewer"
    POLICY_PM = "policy_pm"
    POLICY_APPROVER = "policy_approver"
    OPS_ADMIN = "ops_admin"
    COMPLIANCE_AUDITOR = "compliance_auditor"
    SYSTEM = "system"


# 端点权限映射（对齐设计 §7.3 的子集）。
ENDPOINT_PERMISSIONS: dict[str, set[Role]] = {
    "review.human.queue": {Role.REVIEWER_T1, Role.REVIEWER_T2, Role.REVIEWER_T3, Role.SENIOR_REVIEWER},
    "review.human.decide": {Role.REVIEWER_T1, Role.REVIEWER_T2, Role.REVIEWER_T3, Role.SENIOR_REVIEWER},
    "system.dead_letters": {Role.OPS_ADMIN},
    "audit.read": {Role.COMPLIANCE_AUDITOR, Role.POLICY_PM},
    # Stage 4：策略/维度管理（对齐设计 §7.3 —— Maker(policy_pm) / Checker(policy_approver)）。
    "policy.read": {Role.POLICY_PM, Role.POLICY_APPROVER, Role.OPS_ADMIN, Role.COMPLIANCE_AUDITOR},
    "policy.write": {Role.POLICY_PM},
    "policy.approve": {Role.POLICY_APPROVER},
    "policy.transition": {Role.POLICY_PM, Role.OPS_ADMIN},
}


# --- 密码哈希 ----------------------------------------------------------------

def hash_password(password: str, iterations: int = 200_000) -> str:
    salt = os.urandom(16)
    derived = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"pbkdf2_sha256${iterations}${salt.hex()}${derived.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algorithm, iterations, salt_hex, hash_hex = stored.split("$")
        if algorithm != "pbkdf2_sha256":
            return False
        derived = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(iterations)
        )
    except (ValueError, AttributeError):
        return False
    return hmac.compare_digest(derived.hex(), hash_hex)


# --- 令牌 --------------------------------------------------------------------

def _encode(claims: dict, ttl_seconds: int) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        **claims,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=ttl_seconds)).timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_access_token(user_id: str, roles: list[str]) -> str:
    return _encode({"sub": user_id, "roles": roles, "type": "access"}, settings.access_token_ttl_seconds)


def create_refresh_token(user_id: str) -> str:
    return _encode({"sub": user_id, "type": "refresh"}, settings.refresh_token_ttl_seconds)


def create_ws_token(user_id: str, roles: list[str]) -> dict:
    """WS 握手专用短期令牌（type='ws'，默认 30 分钟）。对齐设计 §7.3。"""
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(seconds=settings.ws_token_ttl_seconds)
    token = _encode({"sub": user_id, "roles": roles, "type": "ws"}, settings.ws_token_ttl_seconds)
    return {"ws_token": token, "expires_at": expires_at.isoformat()}


def decode_token(token: str) -> dict:
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])


def principal_from_ws_token(token: str) -> "Principal":
    """双模式 WS 认证：接受 type='ws'（推荐）或 type='access'（MVP 兼容）。"""
    data = decode_token(token)
    if data.get("type") not in {"ws", "access"}:
        raise jwt.InvalidTokenError("需要 ws 或 access 令牌")
    return Principal(user_id=str(data.get("sub", "")), roles=list(data.get("roles", [])))


# --- FastAPI 依赖 ------------------------------------------------------------

@dataclass(frozen=True)
class Principal:
    user_id: str
    roles: list[str]


def get_current_user(request: Request) -> Principal:
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="缺少或非法的 Authorization 头")
    token = header[7:].strip()
    try:
        data = decode_token(token)
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="令牌无效或已过期")
    if data.get("type") != "access":
        raise HTTPException(status_code=401, detail="需要 access 令牌")
    return Principal(user_id=str(data.get("sub", "")), roles=list(data.get("roles", [])))


def require_permission(name: str):
    """构造一个 RBAC 依赖：先校验 access 令牌，再校验角色命中端点所需权限。"""
    allowed = {role.value for role in ENDPOINT_PERMISSIONS[name]}

    def dependency(user: Principal = Depends(get_current_user)) -> Principal:
        if not (set(user.roles) & allowed):
            raise HTTPException(status_code=403, detail="无权访问该资源")
        return user

    return dependency
