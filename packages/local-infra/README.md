# Local Sandbox Manager

A sandbox manager that runs on local machines (e.g., Mac Mini) to manage sandbox lifecycle operations for Open-Inspect.

## Features

- **Local Sandbox Execution**: Run coding agent sandboxes on local hardware instead of cloud providers
- **Job Queueing**: Manage concurrent sandbox requests with configurable limits
- **State Persistence**: SQLite-based storage for sandbox and snapshot metadata
- **Snapshot Management**: Create and restore sandboxes from filesystem snapshots
- **Security**: API key authentication for all endpoints

## Prerequisites

- Python 3.10+
- Git
- Node.js 22+ (for running sandboxes)
- OpenCode (for coding agent)
- sandbox-runtime package

## Installation

```bash
cd packages/local-infra
pip install -e .
```

Or using uv:

```bash
cd packages/local-infra
uv pip install -e .
```

## Configuration

Environment variables:

| Variable | Description | Default |
|----------|-------------|---------|
| `LOCAL_SANDBOX_API_KEY` | API key for authentication | `local-dev-key` |
| `LOCAL_SANDBOX_DATA_DIR` | Directory for storing sandboxes and snapshots | `/var/local-sandboxes` |
| `LOCAL_SANDBOX_MAX_CONCURRENT` | Maximum concurrent sandboxes | `3` |
| `LOCAL_SANDBOX_TIMEOUT` | Sandbox timeout in seconds | `7200` (2 hours) |

## Running the Server

```bash
export LOCAL_SANDBOX_API_KEY="your-secure-key"
export LOCAL_SANDBOX_DATA_DIR="/path/to/data"
python -m local_sandbox_manager.main
```

The server will start on `http://localhost:8000`.

## API Endpoints

### Health Check

```
GET /health
```

### Create Sandbox

```
POST /create-sandbox
Authorization: Bearer <API_KEY>

{
  "session_id": "string",
  "sandbox_id": "string",
  "repo_owner": "string",
  "repo_name": "string",
  "control_plane_url": "string",
  "sandbox_auth_token": "string",
  "provider": "string",
  "model": "string",
  "user_env_vars": {},
  "branch": "string",
  "code_server_enabled": false,
  "agent_slack_notify_enabled": false
}
```

### Restore Sandbox from Snapshot

```
POST /restore-sandbox
Authorization: Bearer <API_KEY>

{
  "snapshot_image_id": "string",
  "session_id": "string",
  "sandbox_id": "string",
  "sandbox_auth_token": "string",
  "control_plane_url": "string",
  "repo_owner": "string",
  "repo_name": "string",
  "provider": "string",
  "model": "string"
}
```

### Take Snapshot

```
POST /snapshot-sandbox
Authorization: Bearer <API_KEY>

{
  "provider_object_id": "string",
  "session_id": "string",
  "reason": "string"
}
```

### Stop Sandbox

```
POST /stop-sandbox
Authorization: Bearer <API_KEY>

{
  "provider_object_id": "string",
  "session_id": "string"
}
```

### Get Sandbox Status

```
GET /sandbox-status/{provider_object_id}
Authorization: Bearer <API_KEY>
```

## Integration with Open-Inspect Control Plane

To use the local sandbox provider with Open-Inspect:

1. Set `SANDBOX_PROVIDER=local` in your control plane environment
2. Configure these environment variables:
   - `LOCAL_SANDBOX_MANAGER_URL`: URL of the local sandbox manager
   - `LOCAL_SANDBOX_API_KEY`: API key for authentication

## Directory Structure

```
data/
├── sandboxes.db          # SQLite database
├── snapshots/            # Snapshot storage
│   └── <snapshot-id>/    # Individual snapshot
└── workspaces/           # Sandbox workspaces
    └── <sandbox-id>/     # Individual sandbox workspace
```

## Development

```bash
# Install dependencies
uv sync

# Run with auto-reload
uv run uvicorn local_sandbox_manager.main:app --reload
```

## Security Considerations

1. **API Key**: Use a strong, unique API key for production
2. **Network**: Consider running behind a reverse proxy with TLS
3. **Data Storage**: The data directory contains sensitive information - secure it appropriately
4. **Concurrency**: Limit concurrent sandboxes based on available system resources