#!/usr/bin/env python3
"""
Simple test script for /v1/responses API endpoint.
"""

import requests
import json
import os

# Configuration
BASE_URL = "http://localhost:8000"
API_KEY = os.getenv("PROXY_API_KEY", "sk-36fc0c8dc2e2e7f8c02800284deac614250fecce86fea6cd")

headers = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json"
}


def test_basic_request():
    """Test basic /v1/responses request without previous_response_id."""
    print("\n=== Test 1: Basic Request (Codex Format) ===")

    payload = {
        "model": "claude-sonnet-4",
        "input": [
            {
                "type": "message",
                "role": "user",
                "content": "Hello! What's 2+2?"
            }
        ],
        "stream": False,
        "store": True
    }

    response = requests.post(
        f"{BASE_URL}/v1/responses",
        headers=headers,
        json=payload
    )

    print(f"Status: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        print(f"Response ID: {data.get('id')}")
        print(f"Object: {data.get('object')}")
        print(f"Model: {data.get('model')}")
        print(f"Content: {data['choices'][0]['message']['content'][:100]}...")
        return data.get('id')
    else:
        print(f"Error: {response.text}")
        return None


def test_stateful_conversation(previous_response_id):
    """Test stateful conversation using previous_response_id."""
    if not previous_response_id:
        print("\n=== Test 2: Skipped (no previous_response_id) ===")
        return

    print("\n=== Test 2: Stateful Conversation (Codex Format) ===")

    payload = {
        "model": "claude-sonnet-4",
        "input": [
            {
                "type": "message",
                "role": "user",
                "content": "What was my previous question?"
            }
        ],
        "previous_response_id": previous_response_id,
        "stream": False,
        "store": True
    }

    response = requests.post(
        f"{BASE_URL}/v1/responses",
        headers=headers,
        json=payload
    )

    print(f"Status: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        print(f"Response ID: {data.get('id')}")
        print(f"Content: {data['choices'][0]['message']['content'][:200]}...")
    else:
        print(f"Error: {response.text}")


def test_streaming():
    """Test streaming mode with Codex SSE events."""
    print("\n=== Test 3: Streaming Mode (Codex SSE Events) ===")

    payload = {
        "model": "claude-sonnet-4",
        "input": [
            {
                "type": "message",
                "role": "user",
                "content": "Count from 1 to 5."
            }
        ],
        "stream": True,
        "store": False
    }

    response = requests.post(
        f"{BASE_URL}/v1/responses",
        headers=headers,
        json=payload,
        stream=True
    )

    print(f"Status: {response.status_code}")
    if response.status_code == 200:
        print("SSE Events:")
        for line in response.iter_lines():
            if line:
                line_str = line.decode('utf-8')
                if line_str.startswith('event: '):
                    event_type = line_str[7:]
                    print(f"\n[{event_type}]", end=' ')
                elif line_str.startswith('data: '):
                    data_str = line_str[6:]
                    try:
                        event_data = json.loads(data_str)
                        if event_data.get('type') == 'response.text.delta':
                            print(event_data.get('delta', ''), end='', flush=True)
                        elif event_data.get('type') == 'response.done':
                            print(f"\n[Done: {event_data['response']['status']}]")
                    except json.JSONDecodeError:
                        pass
        print("\n[Stream completed]")
    else:
        print(f"Error: {response.text}")


def test_invalid_previous_id():
    """Test with invalid previous_response_id."""
    print("\n=== Test 4: Invalid Previous Response ID ===")

    payload = {
        "model": "claude-sonnet-4",
        "input": [
            {
                "type": "message",
                "role": "user",
                "content": "Hello"
            }
        ],
        "previous_response_id": "resp_invalid_id_12345",
        "stream": False
    }

    response = requests.post(
        f"{BASE_URL}/v1/responses",
        headers=headers,
        json=payload
    )

    print(f"Status: {response.status_code}")
    print(f"Response: {response.text[:200]}")


if __name__ == "__main__":
    print("Testing /v1/responses API endpoint")
    print(f"Base URL: {BASE_URL}")

    # Test 1: Basic request
    response_id = test_basic_request()

    # Test 2: Stateful conversation
    test_stateful_conversation(response_id)

    # Test 3: Streaming
    test_streaming()

    # Test 4: Invalid previous_response_id
    test_invalid_previous_id()

    print("\n=== All tests completed ===")
