# -*- coding: utf-8 -*-

"""
Admin API Routes.

Management endpoints for Kiro Gateway at /api/admin.
Provides credential status, gateway health, model list, and config info.
"""

import json
import time
import uuid
from datetime import datetime, timezone

import cbor2
import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Security
from fastapi.security import APIKeyHeader
from loguru import logger

from pydantic import BaseModel

from kiro.config import (
    APP_VERSION,
    REGION,
    VPN_PROXY_URL,
    SERVER_HOST,
    SERVER_PORT,
)

# --- Security ---
api_key_header = APIKeyHeader(name="Authorization", auto_error=False)


async def verify_api_key(request: Request, auth_header: str = Security(api_key_header)) -> bool:
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid or missing API Key")
    token = auth_header[7:]  # strip "Bearer "
    manager = request.app.state.apikey_manager
    if not manager.verify_key(token):
        raise HTTPException(status_code=401, detail="Invalid or missing API Key")
    return True


# --- API Key CRUD Models ---
class CreateApiKeyRequest(BaseModel):
    name: str

class UpdateApiKeyRequest(BaseModel):
    name: str | None = None
    enabled: bool | None = None


router = APIRouter(prefix="/api/admin")

# Track server start time
_start_time = time.time()

# In-memory import history (cleared on restart)
_import_history: list[dict] = []


@router.get("/status")
async def get_status(request: Request):
    """Gateway status overview."""
    auth = request.app.state.auth_manager
    cache = request.app.state.model_cache

    # Token status
    token_ok = auth._access_token is not None
    token_expiry = None
    if hasattr(auth, '_expires_at') and auth._expires_at:
        token_expiry = auth._expires_at.isoformat()

    return {
        "version": APP_VERSION,
        "uptime_seconds": int(time.time() - _start_time),
        "region": auth.region,
        "auth_type": auth.auth_type.value,
        "token_valid": token_ok,
        "token_expires_at": token_expiry,
        "models_loaded": len(cache.get_all_model_ids()) if cache else 0,
        "proxy_enabled": bool(VPN_PROXY_URL),
        "proxy_url": VPN_PROXY_URL if VPN_PROXY_URL else None,
    }


@router.get("/credentials")
async def get_credentials(request: Request):
    """Current credential status."""
    auth = request.app.state.auth_manager

    token_expiry = None
    expires_in = None
    if hasattr(auth, '_expires_at') and auth._expires_at:
        token_expiry = auth._expires_at.isoformat()
        delta = (auth._expires_at - datetime.now(timezone.utc)).total_seconds()
        expires_in = max(0, int(delta))

    return {
        "auth_type": auth.auth_type.value,
        "region": auth.region,
        "token_valid": auth._access_token is not None,
        "token_expires_at": token_expiry,
        "token_expires_in_seconds": expires_in,
        "profile_arn": auth.profile_arn or None,
        "api_host": auth.api_host,
        "q_host": auth.q_host,
    }


@router.post("/credentials/refresh")
async def refresh_credentials(request: Request):
    """Force token refresh."""
    auth = request.app.state.auth_manager
    try:
        token = await auth.force_refresh()
        return {"success": True, "message": "Token refreshed successfully"}
    except Exception as e:
        logger.error(f"Token refresh failed: {e}")
        raise HTTPException(status_code=500, detail=f"Token refresh failed: {str(e)}")


@router.get("/models")
async def get_models(request: Request):
    """List available models."""
    cache = request.app.state.model_cache
    if not cache:
        return {"models": [], "total": 0}

    models = cache.get_all_model_ids()
    model_details = []
    for model_id in sorted(models):
        info = cache.get(model_id)
        model_details.append({
            "id": model_id,
            "display_name": info.get("displayName", model_id) if info else model_id,
            "provider": info.get("provider", "unknown") if info else "unknown",
        })

    return {"models": model_details, "total": len(model_details)}


@router.get("/config")
async def get_config():
    """Current gateway configuration (sensitive values masked)."""
    return {
        "server_host": SERVER_HOST,
        "server_port": SERVER_PORT,
        "region": REGION,
        "proxy_enabled": bool(VPN_PROXY_URL),
        "proxy_url": VPN_PROXY_URL if VPN_PROXY_URL else None,
        "version": APP_VERSION,
    }


@router.post("/connectivity/test")
async def test_connectivity(request: Request):
    """Test connectivity to Kiro API with a real HTTP request."""
    auth = request.app.state.auth_manager
    start = time.time()
    try:
        token = await auth.get_access_token()

        # Real API call to verify end-to-end connectivity
        from kiro.utils import get_kiro_headers
        from kiro.auth import AuthType
        headers = get_kiro_headers(auth, token)
        params = {"origin": "AI_EDITOR"}
        if auth.auth_type == AuthType.KIRO_DESKTOP and auth.profile_arn:
            params["profileArn"] = auth.profile_arn

        url = f"{auth.q_host}/ListAvailableModels"
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(url, headers=headers, params=params)
            resp.raise_for_status()
            models_count = len(resp.json().get("models", []))

        latency_ms = int((time.time() - start) * 1000)
        return {
            "success": True,
            "latency_ms": latency_ms,
            "auth_type": auth.auth_type.value,
            "region": auth.region,
            "api_host": auth.api_host,
            "models_count": models_count,
        }
    except Exception as e:
        latency_ms = int((time.time() - start) * 1000)
        return {
            "success": False,
            "latency_ms": latency_ms,
            "error": str(e),
        }


class ImportCredentialsRequest(BaseModel):
    credentials: str  # JSON string


@router.post("/credentials/import")
async def import_credentials(request: Request, body: ImportCredentialsRequest):
    """Import credentials from JSON string and hot-reload into auth manager."""
    try:
        data = json.loads(body.credentials)
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {str(e)}")

    if not isinstance(data, dict):
        raise HTTPException(status_code=400, detail="JSON root must be an object")

    auth = request.app.state.auth_manager
    try:
        result = auth.import_credentials(data)
        record = {
            "time": datetime.now(timezone.utc).isoformat(),
            "source": "web_ui",
            "success": True,
            "auth_type": result["auth_type"],
            "region": result["region"],
            "token_valid": result["token_valid"],
        }
        _import_history.insert(0, record)
        logger.info(f"Credentials imported successfully: auth_type={result['auth_type']}, region={result['region']}")
        return {"success": True, **result}
    except Exception as e:
        record = {
            "time": datetime.now(timezone.utc).isoformat(),
            "source": "web_ui",
            "success": False,
            "error": str(e),
        }
        _import_history.insert(0, record)
        logger.error(f"Credentials import failed: {e}")
        raise HTTPException(status_code=500, detail=f"Import failed: {str(e)}")


@router.get("/credentials/import/history")
async def get_import_history():
    """Return credential import history (most recent first)."""
    return {"history": _import_history[:50]}


@router.get("/usage")
async def get_usage(request: Request):
    """Query Kiro account usage and limits via CBOR API."""
    auth = request.app.state.auth_manager
    access_token = auth._access_token
    if not access_token:
        # Return empty usage instead of error when no credentials
        return {"limit": 0, "used": 0, "remaining": 0}

    url = "https://app.kiro.dev/service/KiroWebPortalService/operation/GetUserUsageAndLimits"
    payload = {"isEmailRequired": True, "origin": "KIRO_IDE"}
    headers = {
        "accept": "application/cbor",
        "content-type": "application/cbor",
        "smithy-protocol": "rpc-v2-cbor",
        "amz-sdk-invocation-id": str(uuid.uuid4()),
        "amz-sdk-request": "attempt=1; max=1",
        "x-amz-user-agent": "aws-sdk-js/1.0.0 kiro-account-manager/1.0.0",
        "authorization": f"Bearer {access_token}",
        "cookie": f"Idp=BuilderId; AccessToken={access_token}",
    }

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            logger.debug(f"Usage API request: POST {url}")
            logger.debug(f"Headers: {headers}")
            logger.debug(f"Payload: {payload}")

            resp = await client.post(url, headers=headers, content=cbor2.dumps(payload))

            logger.debug(f"Usage API response: {resp.status_code}")
            logger.debug(f"Response headers: {dict(resp.headers)}")
            logger.debug(f"Response content length: {len(resp.content)} bytes")

        if resp.status_code != 200:
            logger.warning(f"Kiro API returned {resp.status_code} for usage query")
            try:
                error_data = cbor2.loads(resp.content)
                logger.warning(f"Error response data: {error_data}")
            except Exception:
                logger.warning(f"Error response (raw): {resp.content[:200]}")
            return {"limit": 0, "used": 0, "remaining": 0}

        data = cbor2.loads(resp.content)
        logger.debug(f"Usage data: {data}")

        if "__type" in data:
            logger.warning(f"Kiro API error response for usage query: {data}")
            return {"limit": 0, "used": 0, "remaining": 0}

        usage_list = data.get("usageBreakdownList", [])
        credit = next((i for i in usage_list if i.get("resourceType") == "CREDIT"), None)
        if not credit:
            return {"limit": 0, "used": 0, "remaining": 0}

        base_limit = credit.get("usageLimit", 0)
        base_used = credit.get("currentUsage", 0)
        trial_limit, trial_used = 0, 0
        trial_info = credit.get("freeTrialInfo")
        if trial_info and trial_info.get("freeTrialStatus") == "ACTIVE":
            trial_limit = trial_info.get("usageLimit", 0)
            trial_used = trial_info.get("currentUsage", 0)

        total_limit = base_limit + trial_limit
        total_used = base_used + trial_used
        return {"limit": total_limit, "used": total_used, "remaining": total_limit - total_used}

    except Exception as e:
        logger.error(f"Failed to query usage: {e}")
        return {"limit": 0, "used": 0, "remaining": 0}


# --- API Key Management Endpoints ---

@router.get("/apikeys")
async def list_apikeys(request: Request):
    """List all API keys (key field masked), including PROXY_API_KEY from .env."""
    from kiro.config import PROXY_API_KEY

    manager = request.app.state.apikey_manager
    keys = manager.list_keys()

    # Add PROXY_API_KEY from .env as a special entry
    env_key = {
        "id": "env_default",
        "name": "Default API Key (from .env)",
        "key_preview": PROXY_API_KEY[:8] + "..." if len(PROXY_API_KEY) > 8 else PROXY_API_KEY,
        "created_at": "N/A",
        "enabled": True,
    }

    # Insert at the beginning
    return {"keys": [env_key] + keys}


@router.post("/apikeys", status_code=201)
async def create_apikey(request: Request, body: CreateApiKeyRequest):
    """Create a new API key. Returns full key (shown only once)."""
    manager = request.app.state.apikey_manager
    result = manager.create_key(body.name)
    return result


@router.put("/apikeys/{key_id}")
async def update_apikey(request: Request, key_id: str, body: UpdateApiKeyRequest):
    """Update API key name or enabled status."""
    manager = request.app.state.apikey_manager
    result = manager.update_key(key_id, name=body.name, enabled=body.enabled)
    if not result:
        raise HTTPException(status_code=404, detail="API key not found")
    return result


@router.delete("/apikeys/{key_id}", status_code=204)
async def delete_apikey(request: Request, key_id: str):
    """Delete an API key."""
    manager = request.app.state.apikey_manager
    if not manager.delete_key(key_id):
        raise HTTPException(status_code=404, detail="API key not found")


# --- Request History Endpoints ---

@router.get("/history")
async def get_history(request: Request, limit: int = 50, offset: int = 0):
    """Return recent request history (most recent first)."""
    history = request.app.state.request_history
    records, total = history.list(limit=limit, offset=offset)
    return {"records": records, "total": total}


@router.delete("/history")
async def clear_history(request: Request):
    """Clear all request history."""
    history = request.app.state.request_history
    count = history.clear()
    return {"cleared": count}
