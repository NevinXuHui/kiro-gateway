# -*- coding: utf-8 -*-

# Kiro Gateway
# https://github.com/jwadow/kiro-gateway
# Copyright (C) 2025 Jwadow
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.

"""
Utility functions for Kiro Gateway.

Contains functions for fingerprint generation, header formatting,
and other common utilities.
"""

import hashlib
import json
import uuid
from typing import TYPE_CHECKING, List, Dict, Any

from loguru import logger

if TYPE_CHECKING:
    from kiro.auth import KiroAuthManager


def get_machine_fingerprint(credential_hash: str = None) -> str:
    """
    生成或加载与凭证绑定的机器指纹。

    - 导入新凭证时：生成新的随机指纹
    - 重启服务时：如果凭证未变，加载相同的指纹
    - 凭证变更时：生成新的指纹

    Generates or loads a machine fingerprint bound to credentials.
    - On new credential import: generates new random fingerprint
    - On service restart: loads same fingerprint if credentials unchanged
    - On credential change: generates new fingerprint

    Args:
        credential_hash: Hash of current credentials (optional)

    Returns:
        32-character hexadecimal string (random UUID hash)
    """
    from pathlib import Path

    machine_id_file = Path(".machine_id")

    try:
        # 如果提供了凭证哈希，检查是否需要重新生成
        # If credential hash provided, check if regeneration needed
        if credential_hash:
            if machine_id_file.exists():
                content = machine_id_file.read_text().strip()
                if content:
                    lines = content.split('\n')
                    if len(lines) == 2:
                        stored_hash, stored_fingerprint = lines
                        # 凭证未变，返回现有指纹
                        # Credentials unchanged, return existing fingerprint
                        if stored_hash == credential_hash and len(stored_fingerprint) == 32:
                            logger.debug(f"Loaded machine fingerprint for current credentials")
                            return stored_fingerprint

            # 凭证变更或首次导入，生成新指纹
            # Credentials changed or first import, generate new fingerprint
            random_uuid = uuid.uuid4()
            fingerprint = hashlib.sha256(random_uuid.bytes).hexdigest()[:32]

            # 保存凭证哈希和指纹
            # Save credential hash and fingerprint
            machine_id_file.write_text(f"{credential_hash}\n{fingerprint}")
            logger.info(f"Generated new machine fingerprint for new credentials")

            return fingerprint

        # 无凭证哈希，尝试加载现有指纹（用于启动时）
        # No credential hash, try to load existing fingerprint (for startup)
        if machine_id_file.exists():
            content = machine_id_file.read_text().strip()
            if content:
                lines = content.split('\n')
                if len(lines) == 2:
                    fingerprint = lines[1]
                    if len(fingerprint) == 32:
                        logger.debug(f"Loaded machine fingerprint from {machine_id_file}")
                        return fingerprint

        # 回退：生成临时随机指纹（不保存）
        # Fallback: generate temporary random fingerprint (not saved)
        logger.warning("No saved fingerprint found, using temporary random fingerprint")
        return hashlib.sha256(uuid.uuid4().bytes).hexdigest()[:32]

    except Exception as e:
        logger.warning(f"Failed to get/save machine fingerprint: {e}")
        # 回退到随机生成（不保存）
        # Fallback to random generation (not saved)
        return hashlib.sha256(uuid.uuid4().bytes).hexdigest()[:32]


def get_kiro_headers(auth_manager: "KiroAuthManager", token: str) -> dict:
    """
    Builds headers for Kiro API requests.
    
    Includes all necessary headers for authentication and identification:
    - Authorization with Bearer token
    - User-Agent with fingerprint
    - AWS CodeWhisperer specific headers
    
    Args:
        auth_manager: Authentication manager for obtaining fingerprint
        token: Access token for authorization
    
    Returns:
        Dictionary with headers for HTTP request
    """
    fingerprint = auth_manager.fingerprint
    
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "User-Agent": f"aws-sdk-js/1.0.27 ua/2.1 os/win32#10.0.19044 lang/js md/nodejs#22.21.1 api/codewhispererstreaming#1.0.27 m/E KiroIDE-0.7.45-{fingerprint}",
        "x-amz-user-agent": f"aws-sdk-js/1.0.27 KiroIDE-0.7.45-{fingerprint}",
        "x-amzn-codewhisperer-optout": "true",
        "x-amzn-kiro-agent-mode": "vibe",
        "amz-sdk-invocation-id": str(uuid.uuid4()),
        "amz-sdk-request": "attempt=1; max=3",
    }


def generate_completion_id() -> str:
    """
    Generates a unique ID for chat completion.
    
    Returns:
        ID in format "chatcmpl-{uuid_hex}"
    """
    return f"chatcmpl-{uuid.uuid4().hex}"


def generate_conversation_id(messages: List[Dict[str, Any]] = None) -> str:
    """
    Generates a stable conversation ID based on message history.
    
    For truncation recovery, we need a stable ID that persists across requests
    in the same conversation. This is generated from a hash of key messages.
    
    If no messages provided, falls back to random UUID (for backward compatibility).
    
    Args:
        messages: List of messages in the conversation (optional)
    
    Returns:
        Stable conversation ID (16-char hex) or random UUID
    
    Example:
        >>> messages = [
        ...     {"role": "user", "content": "Hello"},
        ...     {"role": "assistant", "content": "Hi there!"}
        ... ]
        >>> conv_id = generate_conversation_id(messages)
        >>> # Same messages will always produce same ID
    """
    if not messages:
        # Fallback to random UUID for backward compatibility
        return str(uuid.uuid4())
    
    # Use first 3 messages + last message for stability
    # This ensures the ID stays the same as conversation grows,
    # but changes if the conversation history is different
    if len(messages) <= 3:
        key_messages = messages
    else:
        key_messages = messages[:3] + [messages[-1]]
    
    # Extract role and first 100 chars of content for hashing
    # This makes the hash stable even if content has minor formatting differences
    simplified_messages = []
    for msg in key_messages:
        role = msg.get("role", "unknown")
        content = msg.get("content", "")
        
        # Handle different content formats (string, list, dict)
        if isinstance(content, str):
            content_str = content[:100]
        elif isinstance(content, list):
            # For Anthropic-style content blocks
            content_str = json.dumps(content, sort_keys=True)[:100]
        else:
            content_str = str(content)[:100]
        
        simplified_messages.append({
            "role": role,
            "content": content_str
        })
    
    # Generate stable hash
    content_json = json.dumps(simplified_messages, sort_keys=True)
    hash_digest = hashlib.sha256(content_json.encode()).hexdigest()
    
    # Return first 16 chars for readability (still 64 bits of entropy)
    return hash_digest[:16]


def generate_tool_call_id() -> str:
    """
    Generates a unique ID for tool call.
    
    Returns:
        ID in format "call_{uuid_hex[:8]}"
    """
    return f"call_{uuid.uuid4().hex[:8]}"