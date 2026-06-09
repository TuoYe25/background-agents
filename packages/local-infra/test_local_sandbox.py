#!/usr/bin/env python3
"""
Test script for Local Sandbox Manager.
Run this script to test the local sandbox provider functionality.
"""

import os
import sys
import json
import requests
import uuid
import time

# Configuration
API_KEY = os.environ.get("LOCAL_SANDBOX_API_KEY", "local-dev-key")
BASE_URL = "http://localhost:8788"

headers = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json",
}


def test_create_sandbox():
    """Test creating a sandbox."""
    print("Testing sandbox creation...")
    
    sandbox_id = f"test-sandbox-{uuid.uuid4().hex[:8]}"
    
    payload = {
        "session_id": f"test-session-{uuid.uuid4().hex[:8]}",
        "sandbox_id": sandbox_id,
        "repo_owner": "test-owner",
        "repo_name": "test-repo",
        "control_plane_url": "http://localhost:8787",
        "sandbox_auth_token": "test-token",
        "provider": "local",
        "model": "gpt-4",
        "branch": "main",
        "code_server_enabled": False,
        "agent_slack_notify_enabled": False,
        "user_env_vars": {},
    }
    
    try:
        response = requests.post(f"{BASE_URL}/create-sandbox", headers=headers, json=payload)
        response.raise_for_status()
        result = response.json()
        
        print(f"OK Sandbox creation request accepted")
        print(f"  Sandbox ID: {result['data']['sandbox_id']}")
        print(f"  Provider Object ID: {result['data']['provider_object_id']}")
        print(f"  Status: {result['data']['status']}")
        
        return result['data']['provider_object_id'], sandbox_id
    except requests.exceptions.RequestException as e:
        print(f"ERR Failed to create sandbox: {e}")
        return None, None


def test_get_status(provider_object_id: str):
    """Test getting sandbox status."""
    print("\nTesting status query...")
    
    try:
        response = requests.get(f"{BASE_URL}/sandbox-status/{provider_object_id}", headers=headers)
        response.raise_for_status()
        result = response.json()
        
        print(f"OK Status retrieved")
        print(f"  Status: {result.get('status')}")
        print(f"  Created at: {result.get('created_at')}")
    except requests.exceptions.RequestException as e:
        print(f"ERR Failed to get status: {e}")


def test_take_snapshot(provider_object_id: str, sandbox_id: str):
    """Test taking a snapshot."""
    print("\nTesting snapshot creation...")
    
    payload = {
        "provider_object_id": provider_object_id,
        "session_id": f"test-session-{uuid.uuid4().hex[:8]}",
        "reason": "test snapshot",
    }
    
    try:
        response = requests.post(f"{BASE_URL}/snapshot-sandbox", headers=headers, json=payload)
        response.raise_for_status()
        result = response.json()
        
        print(f"OK Snapshot created")
        print(f"  Snapshot ID: {result['data']['image_id']}")
        
        return result['data']['image_id']
    except requests.exceptions.RequestException as e:
        print(f"ERR Failed to create snapshot: {e}")
        return None


def test_stop_sandbox(provider_object_id: str):
    """Test stopping a sandbox."""
    print("\nTesting sandbox stop...")
    
    payload = {
        "provider_object_id": provider_object_id,
        "session_id": f"test-session-{uuid.uuid4().hex[:8]}",
    }
    
    try:
        response = requests.post(f"{BASE_URL}/stop-sandbox", headers=headers, json=payload)
        response.raise_for_status()
        result = response.json()
        
        print(f"OK Sandbox stopped")
        print(f"  Success: {result['success']}")
    except requests.exceptions.RequestException as e:
        print(f"ERR Failed to stop sandbox: {e}")


def test_list_sandboxes():
    """Test listing sandboxes."""
    print("\nTesting sandbox listing...")
    
    try:
        response = requests.get(f"{BASE_URL}/list-sandboxes", headers=headers)
        response.raise_for_status()
        result = response.json()
        
        print(f"OK Sandboxes listed")
        print(f"  Total sandboxes: {len(result['sandboxes'])}")
        for sb in result['sandboxes']:
            print(f"  - {sb['sandbox_id']}: {sb['status']}")
    except requests.exceptions.RequestException as e:
        print(f"ERR Failed to list sandboxes: {e}")


def main():
    print("=" * 60)
    print("Local Sandbox Manager Test Script")
    print("=" * 60)
    print()
    
    # Check if server is running
    try:
        response = requests.get(f"{BASE_URL}/health", headers=headers)
        if response.status_code == 200:
            print("OK Local Sandbox Manager is running")
        else:
            print("ERR Local Sandbox Manager is not responding properly")
            sys.exit(1)
    except requests.exceptions.RequestException:
        print("ERR Local Sandbox Manager is not running. Please start it first.")
        print("  Run: python src/main.py")
        sys.exit(1)
    
    print()
    
    # Run tests
    provider_object_id, sandbox_id = test_create_sandbox()
    
    if provider_object_id:
        time.sleep(3)  # Wait for sandbox to be created
        test_get_status(provider_object_id)
        snapshot_id = test_take_snapshot(provider_object_id, sandbox_id)
        test_stop_sandbox(provider_object_id)
        test_list_sandboxes()
    
    print("\n" + "=" * 60)
    print("Test completed!")
    print("=" * 60)


if __name__ == "__main__":
    main()