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
FastAPI routes for Kiro Gateway.

Contains all API endpoints:
- / and /health: Health check
- /v1/models: Models list
- /v1/chat/completions: Chat completions
"""

import json
import time
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, Security
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.security import APIKeyHeader
from loguru import logger

from kiro.config import APP_VERSION
from kiro.models_openai import (
    OpenAIModel,
    ModelList,
    ChatCompletionRequest,
    ResponsesRequest,
    ResponseInputMessage,
)
from kiro.auth import KiroAuthManager, AuthType
from kiro.cache import ModelInfoCache
from kiro.model_resolver import ModelResolver
from kiro.converters_openai import build_kiro_payload
from kiro.streaming_openai import stream_kiro_to_openai, collect_stream_response, stream_with_first_token_retry
from kiro.http_client import KiroHttpClient
from kiro.utils import generate_conversation_id

# Import debug_logger
try:
    from kiro.debug_logger import debug_logger
except ImportError:
    debug_logger = None


def _record_history(request: Request, model: str, stream: bool, status_code: int, start_time: float, error: str = None):
    """Record request to history store (best-effort, never raises)."""
    try:
        history = request.app.state.request_history
        latency_ms = int((time.time() - start_time) * 1000)
        history.record(
            endpoint="/v1/chat/completions",
            method="POST",
            model=model,
            stream=stream,
            status_code=status_code,
            latency_ms=latency_ms,
            error=error,
        )
    except Exception:
        pass


# --- Security scheme ---
api_key_header = APIKeyHeader(name="Authorization", auto_error=False)


async def verify_api_key(request: Request, auth_header: str = Security(api_key_header)) -> bool:
    """
    Verify API key in Authorization header via ApiKeyManager.

    Expects format: "Bearer {key}"
    """
    if not auth_header or not auth_header.startswith("Bearer "):
        logger.warning("Access attempt with invalid API key.")
        raise HTTPException(status_code=401, detail="Invalid or missing API Key")
    token = auth_header[7:]
    manager = request.app.state.apikey_manager
    if not manager.verify_key(token):
        logger.warning("Access attempt with invalid API key.")
        raise HTTPException(status_code=401, detail="Invalid or missing API Key")
    return True


# --- Router ---
router = APIRouter()


@router.get("/")
async def root():
    """
    Health check endpoint.
    
    Returns:
        Status and application version
    """
    return {
        "status": "ok",
        "message": "Kiro Gateway is running",
        "version": APP_VERSION
    }


@router.get("/health")
async def health():
    """
    Detailed health check.
    
    Returns:
        Status, timestamp and version
    """
    return {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "version": APP_VERSION
    }

@router.get("/v1/models", response_model=ModelList, dependencies=[Depends(verify_api_key)])
async def get_models(request: Request):
    """
    Return list of available models.
    
    Models are loaded at startup (blocking) and cached.
    This endpoint returns the cached list.
    
    Args:
        request: FastAPI Request for accessing app.state
    
    Returns:
        ModelList with available models in consistent format (with dots)
    """
    logger.info("Request to /v1/models")
    
    model_resolver: ModelResolver = request.app.state.model_resolver
    
    # Get all available models from resolver (cache + hidden models)
    available_model_ids = model_resolver.get_available_models()
    
    # Build OpenAI-compatible model list
    openai_models = [
        OpenAIModel(
            id=model_id,
            owned_by="anthropic",
            description="Claude model via Kiro API"
        )
        for model_id in available_model_ids
    ]
    
    return ModelList(data=openai_models)


@router.post("/v1/chat/completions", dependencies=[Depends(verify_api_key)])
async def chat_completions(request: Request, request_data: ChatCompletionRequest):
    """
    Chat completions endpoint - compatible with OpenAI API.
    
    Accepts requests in OpenAI format and translates them to Kiro API.
    Supports streaming and non-streaming modes.
    
    Args:
        request: FastAPI Request for accessing app.state
        request_data: Request in OpenAI ChatCompletionRequest format
    
    Returns:
        StreamingResponse for streaming mode
        JSONResponse for non-streaming mode
    
    Raises:
        HTTPException: On validation or API errors
    """
    logger.info(f"Request to /v1/chat/completions (model={request_data.model}, stream={request_data.stream})")

    _req_start_time = time.time()

    auth_manager: KiroAuthManager = request.app.state.auth_manager
    model_cache: ModelInfoCache = request.app.state.model_cache
    
    # Note: prepare_new_request() and log_request_body() are now called by DebugLoggerMiddleware
    # This ensures debug logging works even for requests that fail Pydantic validation (422 errors)
    
    # Check for truncation recovery opportunities
    from kiro.truncation_state import get_tool_truncation, get_content_truncation
    from kiro.truncation_recovery import generate_truncation_tool_result, generate_truncation_user_message
    from kiro.models_openai import ChatMessage
    
    modified_messages = []
    tool_results_modified = 0
    content_notices_added = 0
    
    for msg in request_data.messages:
        # Check if this is a tool_result for a truncated tool call
        if msg.role == "tool" and msg.tool_call_id:
            truncation_info = get_tool_truncation(msg.tool_call_id)
            if truncation_info:
                # Modify tool_result content to include truncation notice
                synthetic = generate_truncation_tool_result(
                    tool_name=truncation_info.tool_name,
                    tool_use_id=msg.tool_call_id,
                    truncation_info=truncation_info.truncation_info
                )
                # Prepend truncation notice to original content
                modified_content = f"{synthetic['content']}\n\n---\n\nOriginal tool result:\n{msg.content}"
                
                # Create NEW ChatMessage object (Pydantic immutability)
                modified_msg = msg.model_copy(update={"content": modified_content})
                modified_messages.append(modified_msg)
                tool_results_modified += 1
                logger.debug(f"Modified tool_result for {msg.tool_call_id} to include truncation notice")
                continue  # Skip normal append since we already added modified version
        
        # Check if this is an assistant message with truncated content
        if msg.role == "assistant" and msg.content and isinstance(msg.content, str):
            truncation_info = get_content_truncation(msg.content)
            if truncation_info:
                # Add this message first
                modified_messages.append(msg)
                # Then add synthetic user message about truncation
                synthetic_user_msg = ChatMessage(
                    role="user",
                    content=generate_truncation_user_message()
                )
                modified_messages.append(synthetic_user_msg)
                content_notices_added += 1
                logger.debug(f"Added truncation notice after assistant message (hash: {truncation_info.message_hash})")
                continue  # Skip normal append since we already added it
        
        modified_messages.append(msg)
    
    if tool_results_modified > 0 or content_notices_added > 0:
        request_data.messages = modified_messages
        logger.info(f"Truncation recovery: modified {tool_results_modified} tool_result(s), added {content_notices_added} content notice(s)")
    
    # Generate conversation ID for Kiro API (random UUID, not used for tracking)
    conversation_id = generate_conversation_id()
    
    # Build payload for Kiro
    # profileArn is only needed for Kiro Desktop auth
    # AWS SSO OIDC (Builder ID) users don't need profileArn and it causes 403 if sent
    profile_arn_for_payload = ""
    if auth_manager.auth_type == AuthType.KIRO_DESKTOP and auth_manager.profile_arn:
        profile_arn_for_payload = auth_manager.profile_arn
    
    try:
        kiro_payload = build_kiro_payload(
            request_data,
            conversation_id,
            profile_arn_for_payload
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    # Log Kiro payload
    try:
        kiro_request_body = json.dumps(kiro_payload, ensure_ascii=False, indent=2).encode('utf-8')
        if debug_logger:
            debug_logger.log_kiro_request_body(kiro_request_body)
    except Exception as e:
        logger.warning(f"Failed to log Kiro request: {e}")
    
    # Create HTTP client with retry logic
    # For streaming: use per-request client to avoid CLOSE_WAIT leak on VPN disconnect (issue #54)
    # For non-streaming: use shared client for connection pooling
    url = f"{auth_manager.api_host}/generateAssistantResponse"
    logger.debug(f"Kiro API URL: {url}")
    
    if request_data.stream:
        # Streaming mode: per-request client prevents orphaned connections
        # when network interface changes (VPN disconnect/reconnect)
        http_client = KiroHttpClient(auth_manager, shared_client=None)
    else:
        # Non-streaming mode: shared client for efficient connection reuse
        shared_client = request.app.state.http_client
        http_client = KiroHttpClient(auth_manager, shared_client=shared_client)
    try:
        # Make request to Kiro API (for both streaming and non-streaming modes)
        # Important: we wait for Kiro response BEFORE returning StreamingResponse,
        # so that 200 OK means Kiro accepted the request and started responding
        response = await http_client.request_with_retry(
            "POST",
            url,
            kiro_payload,
            stream=True
        )
        
        if response.status_code != 200:
            try:
                error_content = await response.aread()
            except Exception:
                error_content = b"Unknown error"
            
            await http_client.close()
            error_text = error_content.decode('utf-8', errors='replace')
            
            # Try to parse JSON response from Kiro to extract error message
            error_message = error_text
            try:
                error_json = json.loads(error_text)
                # Enhance Kiro API errors with user-friendly messages
                from kiro.kiro_errors import enhance_kiro_error
                error_info = enhance_kiro_error(error_json)
                error_message = error_info.user_message
                # Log original error for debugging
                logger.debug(f"Original Kiro error: {error_info.original_message} (reason: {error_info.reason})")
            except (json.JSONDecodeError, KeyError):
                pass
            
            # Log access log for error (before flush, so it gets into app_logs)
            logger.warning(
                f"HTTP {response.status_code} - POST /v1/chat/completions - {error_message[:100]}"
            )
            
            # Flush debug logs on error ("errors" mode)
            if debug_logger:
                debug_logger.flush_on_error(response.status_code, error_message)
            
            # Return error in OpenAI API format
            _record_history(request, request_data.model, request_data.stream, response.status_code, _req_start_time, error_message[:200])
            return JSONResponse(
                status_code=response.status_code,
                content={
                    "error": {
                        "message": error_message,
                        "type": "kiro_api_error",
                        "code": response.status_code
                    }
                }
            )
        
        # Prepare data for fallback token counting
        # Convert Pydantic models to dicts for tokenizer
        messages_for_tokenizer = [msg.model_dump() for msg in request_data.messages]
        tools_for_tokenizer = [tool.model_dump() for tool in request_data.tools] if request_data.tools else None
        
        if request_data.stream:
            # Streaming mode
            async def stream_wrapper():
                streaming_error = None
                client_disconnected = False
                try:
                    async for chunk in stream_kiro_to_openai(
                        http_client.client,
                        response,
                        request_data.model,
                        model_cache,
                        auth_manager,
                        request_messages=messages_for_tokenizer,
                        request_tools=tools_for_tokenizer
                    ):
                        yield chunk
                except GeneratorExit:
                    # Client disconnected - this is normal
                    client_disconnected = True
                    logger.debug("Client disconnected during streaming (GeneratorExit in routes)")
                except Exception as e:
                    streaming_error = e
                    # Try to send [DONE] to client before finishing
                    # so client doesn't "hang" waiting for data
                    try:
                        yield "data: [DONE]\n\n"
                    except Exception:
                        pass  # Client already disconnected
                    raise
                finally:
                    await http_client.close()
                    # Record request history
                    if streaming_error:
                        _record_history(request, request_data.model, True, 500, _req_start_time, str(streaming_error)[:200])
                    else:
                        _record_history(request, request_data.model, True, 200, _req_start_time)
                    # Log access log for streaming (success or error)
                    if streaming_error:
                        error_type = type(streaming_error).__name__
                        error_msg = str(streaming_error) if str(streaming_error) else "(empty message)"
                        logger.error(f"HTTP 500 - POST /v1/chat/completions (streaming) - [{error_type}] {error_msg[:100]}")
                    elif client_disconnected:
                        logger.info(f"HTTP 200 - POST /v1/chat/completions (streaming) - client disconnected")
                    else:
                        logger.info(f"HTTP 200 - POST /v1/chat/completions (streaming) - completed")
                    # Write debug logs AFTER streaming completes
                    if debug_logger:
                        if streaming_error:
                            debug_logger.flush_on_error(500, str(streaming_error))
                        else:
                            debug_logger.discard_buffers()
            
            return StreamingResponse(stream_wrapper(), media_type="text/event-stream")
        
        else:
            
            # Non-streaming mode - collect entire response
            openai_response = await collect_stream_response(
                http_client.client,
                response,
                request_data.model,
                model_cache,
                auth_manager,
                request_messages=messages_for_tokenizer,
                request_tools=tools_for_tokenizer
            )
            
            await http_client.close()

            # Record request history
            _record_history(request, request_data.model, False, 200, _req_start_time)

            # Log access log for non-streaming success
            logger.info(f"HTTP 200 - POST /v1/chat/completions (non-streaming) - completed")
            
            # Write debug logs after non-streaming request completes
            if debug_logger:
                debug_logger.discard_buffers()
            
            return JSONResponse(content=openai_response)
    
    except HTTPException as e:
        await http_client.close()
        _record_history(request, request_data.model, request_data.stream, e.status_code, _req_start_time, str(e.detail)[:200])
        # Log access log for HTTP error
        logger.error(f"HTTP {e.status_code} - POST /v1/chat/completions - {e.detail}")
        # Flush debug logs on HTTP error ("errors" mode)
        if debug_logger:
            debug_logger.flush_on_error(e.status_code, str(e.detail))
        raise
    except Exception as e:
        await http_client.close()
        _record_history(request, request_data.model, request_data.stream, 500, _req_start_time, str(e)[:200])
        logger.error(f"Internal error: {e}", exc_info=True)
        # Log access log for internal error
        logger.error(f"HTTP 500 - POST /v1/chat/completions - {str(e)[:100]}")
        # Flush debug logs on internal error ("errors" mode)
        if debug_logger:
            debug_logger.flush_on_error(500, str(e))
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")


@router.post("/v1/responses", dependencies=[Depends(verify_api_key)])
async def responses(request: Request, request_data: ResponsesRequest):
    """
    OpenAI Responses API endpoint - stateful conversation interface.

    Unifies Chat Completions and Assistants capabilities with stateful conversations.
    Supports previous_response_id for automatic context management.

    Args:
        request: FastAPI Request for accessing app.state
        request_data: Request in OpenAI ResponsesRequest format

    Returns:
        StreamingResponse for streaming mode
        JSONResponse for non-streaming mode

    Raises:
        HTTPException: On validation or API errors
    """
    from kiro.models_openai import ResponsesRequest, ChatMessage

    logger.info(f"Request to /v1/responses (model={request_data.model}, stream={request_data.stream}, previous_response_id={request_data.previous_response_id})")

    _req_start_time = time.time()

    auth_manager: KiroAuthManager = request.app.state.auth_manager
    model_cache: ModelInfoCache = request.app.state.model_cache
    response_store = request.app.state.response_store

    # Build full message history
    messages = []

    # Load previous conversation if previous_response_id provided
    if request_data.previous_response_id:
        previous_state = response_store.get(request_data.previous_response_id)
        if not previous_state:
            raise HTTPException(
                status_code=404,
                detail=f"Previous response ID not found: {request_data.previous_response_id}"
            )
        # Add previous messages
        messages.extend(previous_state.get("messages", []))
        logger.debug(f"Loaded {len(messages)} message(s) from previous response {request_data.previous_response_id}")

    # Add new input messages (convert from Codex format to ChatMessage format)
    for msg in request_data.input:
        # Codex format: {"type": "message", "role": "user", "content": "..."}
        # Convert to: {"role": "user", "content": "..."}
        message_dict = {"role": msg.role, "content": msg.content}
        messages.append(message_dict)

    # Convert to ChatCompletionRequest format for reusing existing logic
    from kiro.models_openai import ChatCompletionRequest
    chat_request = ChatCompletionRequest(
        model=request_data.model,
        messages=[ChatMessage(**msg) for msg in messages],
        stream=request_data.stream,
        temperature=request_data.temperature,
        top_p=request_data.top_p,
        max_tokens=request_data.max_tokens or request_data.max_completion_tokens,
        stop=request_data.stop,
        tools=request_data.tools,
        tool_choice=request_data.tool_choice,
        presence_penalty=request_data.presence_penalty,
        frequency_penalty=request_data.frequency_penalty,
        n=request_data.n,
        user=request_data.user,
    )

    # Generate conversation ID for Kiro API
    conversation_id = generate_conversation_id()

    # Build payload for Kiro
    profile_arn_for_payload = ""
    if auth_manager.auth_type == AuthType.KIRO_DESKTOP and auth_manager.profile_arn:
        profile_arn_for_payload = auth_manager.profile_arn

    try:
        kiro_payload = build_kiro_payload(
            chat_request,
            conversation_id,
            profile_arn_for_payload
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Create HTTP client
    url = f"{auth_manager.api_host}/generateAssistantResponse"

    if request_data.stream:
        http_client = KiroHttpClient(auth_manager, shared_client=None)
    else:
        shared_client = request.app.state.http_client
        http_client = KiroHttpClient(auth_manager, shared_client=shared_client)

    try:
        # Make request to Kiro API
        response = await http_client.request_with_retry(
            "POST",
            url,
            kiro_payload,
            stream=True
        )

        if response.status_code != 200:
            try:
                error_content = await response.aread()
            except Exception:
                error_content = b"Unknown error"

            await http_client.close()
            error_text = error_content.decode('utf-8', errors='replace')

            try:
                error_json = json.loads(error_text)
                from kiro.kiro_errors import enhance_kiro_error
                error_info = enhance_kiro_error(error_json)
                error_message = error_info.user_message
            except (json.JSONDecodeError, KeyError):
                error_message = error_text

            _record_history(request, request_data.model, request_data.stream, response.status_code, _req_start_time, error_message[:200])
            return JSONResponse(
                status_code=response.status_code,
                content={
                    "error": {
                        "message": error_message,
                        "type": "kiro_api_error",
                        "code": response.status_code
                    }
                }
            )

        # Prepare data for token counting
        messages_for_tokenizer = [msg.model_dump() for msg in chat_request.messages]
        tools_for_tokenizer = [tool.model_dump() for tool in chat_request.tools] if chat_request.tools else None

        if request_data.stream:
            # Streaming mode with Codex SSE event format
            response_id = f"resp_{uuid.uuid4().hex}"
            assistant_message_content = []
            first_chunk = True

            async def stream_wrapper():
                nonlocal first_chunk
                streaming_error = None
                try:
                    async for chunk in stream_kiro_to_openai(
                        http_client.client,
                        response,
                        request_data.model,
                        model_cache,
                        auth_manager,
                        request_messages=messages_for_tokenizer,
                        request_tools=tools_for_tokenizer
                    ):
                        chunk_str = chunk.removeprefix("data: ")
                        if chunk_str.strip() == "[DONE]":
                            # Send response.done event
                            done_event = {
                                "type": "response.done",
                                "response": {
                                    "id": response_id,
                                    "object": "response",
                                    "status": "completed"
                                }
                            }
                            yield f"event: response.done\ndata: {json.dumps(done_event)}\n\n"
                        else:
                            chunk_data = json.loads(chunk_str)

                            # Send response.output_item.added on first chunk
                            if first_chunk and chunk_data.get("choices"):
                                first_chunk = False
                                output_item_event = {
                                    "type": "response.output_item.added",
                                    "item": {
                                        "id": f"item_{uuid.uuid4().hex[:8]}",
                                        "type": "message",
                                        "role": "assistant",
                                        "content": []
                                    }
                                }
                                yield f"event: response.output_item.added\ndata: {json.dumps(output_item_event)}\n\n"

                            # Send response.text.delta for content
                            if chunk_data.get("choices"):
                                delta_content = chunk_data["choices"][0].get("delta", {}).get("content")
                                if delta_content:
                                    assistant_message_content.append(delta_content)
                                    text_delta_event = {
                                        "type": "response.text.delta",
                                        "delta": delta_content
                                    }
                                    yield f"event: response.text.delta\ndata: {json.dumps(text_delta_event)}\n\n"

                                # Handle tool calls
                                tool_calls = chunk_data["choices"][0].get("delta", {}).get("tool_calls")
                                if tool_calls:
                                    for tool_call in tool_calls:
                                        if tool_call.get("function", {}).get("arguments"):
                                            func_args_event = {
                                                "type": "response.function_call_arguments.delta",
                                                "delta": tool_call["function"]["arguments"],
                                                "call_id": tool_call.get("id")
                                            }
                                            yield f"event: response.function_call_arguments.delta\ndata: {json.dumps(func_args_event)}\n\n"
                except GeneratorExit:
                    logger.debug("Client disconnected during streaming (GeneratorExit)")
                except Exception as e:
                    streaming_error = e
                    # Send error event
                    error_event = {
                        "type": "response.error",
                        "error": {
                            "message": str(e),
                            "type": "server_error"
                        }
                    }
                    try:
                        yield f"event: response.error\ndata: {json.dumps(error_event)}\n\n"
                    except Exception:
                        pass
                    raise
                finally:
                    await http_client.close()

                    # Store conversation state if requested
                    if request_data.store and not streaming_error:
                        full_assistant_content = "".join(assistant_message_content)
                        updated_messages = messages + [{"role": "assistant", "content": full_assistant_content}]
                        response_store.create(
                            messages=updated_messages,
                            model=request_data.model,
                            metadata=request_data.metadata
                        )

                    if streaming_error:
                        _record_history(request, request_data.model, True, 500, _req_start_time, str(streaming_error)[:200])
                    else:
                        _record_history(request, request_data.model, True, 200, _req_start_time)

            return StreamingResponse(stream_wrapper(), media_type="text/event-stream")

        else:
            # Non-streaming mode
            openai_response = await collect_stream_response(
                http_client.client,
                response,
                request_data.model,
                model_cache,
                auth_manager,
                request_messages=messages_for_tokenizer,
                request_tools=tools_for_tokenizer
            )

            await http_client.close()

            # Store conversation state if requested and get response_id
            if request_data.store:
                assistant_message = openai_response["choices"][0]["message"]
                updated_messages = messages + [assistant_message]
                response_id = response_store.create(
                    messages=updated_messages,
                    model=request_data.model,
                    metadata=request_data.metadata
                )
            else:
                response_id = f"resp_{uuid.uuid4().hex}"

            # Convert to ResponsesResponse format
            openai_response["object"] = "response"
            openai_response["id"] = response_id

            _record_history(request, request_data.model, False, 200, _req_start_time)
            logger.info(f"HTTP 200 - POST /v1/responses (non-streaming) - completed")

            return JSONResponse(content=openai_response)

    except HTTPException as e:
        await http_client.close()
        _record_history(request, request_data.model, request_data.stream, e.status_code, _req_start_time, str(e.detail)[:200])
        logger.error(f"HTTP {e.status_code} - POST /v1/responses - {e.detail}")
        raise
    except Exception as e:
        await http_client.close()
        _record_history(request, request_data.model, request_data.stream, 500, _req_start_time, str(e)[:200])
        logger.error(f"Internal error: {e}", exc_info=True)
        logger.error(f"HTTP 500 - POST /v1/responses - {str(e)[:100]}")
        raise HTTPException(status_code=500, detail=str(e))