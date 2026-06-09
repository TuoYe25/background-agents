# Local Sandbox Provider

The Local Sandbox Provider enables Open-Inspect to run sandboxes on local machines (e.g., Mac Mini) instead of cloud providers like Modal. This is particularly useful for:

- Full closed-loop build/run/test/screenshot/eval from local repositories (e.g., Electron.js apps)
- Lower latency for local development workflows
- Working with private repos that cannot be accessed from the cloud
- Running applications that require local hardware access
- Cost savings for development and testing

## Architecture Overview

The local sandbox provider follows the same pluggable architecture as other sandbox providers:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         Control Plane                                 │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │              SandboxLifecycleManager                           │  │
│  │         (spawn, restore, snapshot, stop)                      │  │
│  └─────────────────────────────┬──────────────────────────────────┘  │
└─────────────────────────────────┼─────────────────────────────────────┘
                                  │ HTTP API
                                  ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                     Local Sandbox Manager                             │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────────┐   │
│  │  Job Queue  │──│  Sandbox    │──│       SQLite Database       │   │
│  │ (max 100)   │  │ Manager     │   │ (sandboxes, snapshots)     │   │
│  └─────────────┘  └──────┬──────┘  └─────────────────────────────┘   │
│                          │                                           │
│                          ▼                                           │
│              ┌───────────────────────┐                               │
│              │   Active Sandboxes    │                               │
│              │   (max configurable)  │                               │
│              │   ┌─────┬─────┬─────┐│                               │
│              │   │ SB1 │ SB2 │ SB3 ││                               │
│              │   └─────┴─────┴─────┘│                               │
│              └───────────────────────┘                               │
└─────────────────────────────────────────────────────────────────────────┘
```

## How It Works

### 1. Provider Selection

The control plane selects the sandbox provider based on the `SANDBOX_PROVIDER` environment variable:

| Value | Provider | Description |
|-------|----------|-------------|
| `modal` | ModalSandboxProvider | Cloud-based sandboxes (default) |
| `daytona` | DaytonaSandboxProvider | Daytona cloud sandboxes |
| `vercel` | VercelSandboxProvider | Vercel cloud sandboxes |
| `local` | LocalSandboxProvider | Local machine sandboxes |

### 2. Request Flow

1. Client sends a prompt to the control plane
2. Control plane's `SandboxLifecycleManager` evaluates the spawn decision
3. If `SANDBOX_PROVIDER=local`, the `LocalSandboxProvider` is used
4. The provider communicates with the local sandbox manager via HTTP
5. Local sandbox manager queues the request (if max concurrency reached)
6. Sandbox is created on the local machine
7. OpenCode agent runs in the sandbox
8. Results are streamed back to the control plane

### 3. Coexistence with Modal Infrastructure

The local provider coexists seamlessly with the original Modal infrastructure:

- **Per-session provider selection**: Different sessions can use different providers
- **Shared control plane**: Same control plane code handles all providers
- **Shared session state**: Session state is stored in Cloudflare Durable Objects regardless of provider
- **Shared API**: All clients (web, Slack, GitHub) work with any provider
- **Snapshot compatibility**: Snapshots are stored locally for local sandboxes

## Setup Guide

### Prerequisites

1. **Local Machine Requirements**:
   - macOS (Intel/M1/M2/M3), Linux, or Windows
   - Python 3.10+
   - Node.js 22+
   - Git
   - OpenCode (coding agent)
   - sandbox-runtime package

2. **Control Plane Requirements**:
   - Cloudflare Workers deployment
   - `SANDBOX_PROVIDER=local` environment variable
   - Local sandbox manager URL and API key

### Step 1: Install Local Sandbox Manager

```bash
cd packages/local-infra
uv pip install -e .
```

### Development Mode (Testing Without Mac Mini)

For testing on your local development machine without needing a Mac Mini or the full OpenCode infrastructure, you can enable **development mode**:

```bash
# Set environment variables for development
export LOCAL_SANDBOX_API_KEY="local-dev-key"
export LOCAL_SANDBOX_MAX_CONCURRENT="1"
export LOCAL_SANDBOX_DEV_MODE="true"

# Start the local sandbox manager
python -m local_sandbox_manager.main
```

**Windows users**: Use the provided batch script:
```bash
start-local-manager.bat
```

**Development Mode Features**:
- Skips git clone operations (creates test files instead)
- Skips sandbox runtime startup
- Reduces resource requirements for testing
- All API endpoints still work normally
- Perfect for testing the control plane integration

### Testing the Local Sandbox Manager

Run the test script to verify everything works:

```bash
python test_local_sandbox.py
```

The test script will:
1. Check if the local sandbox manager is running
2. Create a test sandbox
3. Query sandbox status
4. Take a snapshot
5. Stop the sandbox
6. List all sandboxes

### Step 2: Configure Environment Variables

```bash
# On the local machine
export LOCAL_SANDBOX_API_KEY="your-secure-api-key"
export LOCAL_SANDBOX_DATA_DIR="/var/local-sandboxes"
export LOCAL_SANDBOX_MAX_CONCURRENT="3"
export LOCAL_SANDBOX_TIMEOUT="7200"
```

### Step 3: Start the Local Sandbox Manager

```bash
python -m local_sandbox_manager.main
```

The server will start on `http://localhost:8000`.

### Step 4: Configure Control Plane

Add these environment variables to your Cloudflare Workers deployment:

| Variable | Description | Example |
|----------|-------------|---------|
| `SANDBOX_PROVIDER` | Set to `local` | `local` |
| `LOCAL_SANDBOX_MANAGER_URL` | URL of the local sandbox manager | `http://your-mac-mini.local:8000` |
| `LOCAL_SANDBOX_API_KEY` | API key for authentication | `your-secure-api-key` |

### Step 5: Expose Local Manager to Control Plane

If your control plane is deployed on Cloudflare and your local machine is behind a firewall, you'll need to expose the local manager:

**Option A: Port forwarding (recommended for development)**
```bash
# Using ngrok
ngrok http 8000
```

**Option B: VPN connection**
- Use Tailscale or similar VPN to connect your local machine to the cloud network

**Option C: Direct network access**
- Ensure your local machine has a public IP or is accessible via your organization's network

## Configuration Reference

### Local Sandbox Manager Configuration

| Environment Variable | Description | Default |
|----------------------|-------------|---------|
| `LOCAL_SANDBOX_API_KEY` | API key for authentication | `local-dev-key` |
| `LOCAL_SANDBOX_DATA_DIR` | Directory for storing sandboxes and snapshots | `/var/local-sandboxes` |
| `LOCAL_SANDBOX_MAX_CONCURRENT` | Maximum concurrent sandboxes | `3` |
| `LOCAL_SANDBOX_TIMEOUT` | Sandbox timeout in seconds | `7200` (2 hours) |

### Control Plane Configuration

| Environment Variable | Description | Required |
|----------------------|-------------|----------|
| `SANDBOX_PROVIDER` | Must be set to `local` | Yes |
| `LOCAL_SANDBOX_MANAGER_URL` | URL of the local sandbox manager | Yes |
| `LOCAL_SANDBOX_API_KEY` | API key for authentication | Yes |

## Lifecycle Management

### Sandbox States

```
pending → spawning → connecting → running → stopped
                              ↘ failed
                              ↘ stale
```

### State Transitions

1. **pending**: Initial state before spawn request
2. **spawning**: Sandbox creation is in progress
3. **connecting**: Sandbox created, waiting for bridge connection
4. **running**: Sandbox is active and ready to receive prompts
5. **stopped**: Sandbox stopped due to inactivity timeout
6. **failed**: Sandbox failed to start or encountered an error
7. **stale**: Sandbox heartbeat timed out

### Timeouts

| Timeout | Description | Default |
|----------|-------------|---------|
| Connecting timeout | Time to wait for sandbox bridge to connect | 30 seconds |
| Heartbeat timeout | Time to wait for heartbeat before marking stale | 60 seconds |
| Inactivity timeout | Time to wait before stopping idle sandbox | 2 hours |

## Job Queueing System

The local sandbox manager includes a built-in job queue:

### Features

- **Concurrent execution**: Configurable maximum concurrent sandboxes
- **Queue depth**: Maximum 100 pending requests
- **Fair scheduling**: FIFO ordering of requests
- **Backpressure handling**: Queue prevents resource exhaustion

### Queue Behavior

1. When a sandbox request arrives, it's added to the queue
2. Worker processes dequeue requests when capacity is available
3. If queue is full (100 items), new requests are rejected
4. Active sandboxes are tracked to enforce concurrency limits

## State Persistence

### Database Schema

**sandboxes table**:
- `id`: Unique identifier
- `provider_object_id`: Local manager's sandbox ID
- `session_id`: Control plane session ID
- `sandbox_id`: Logical sandbox ID
- `repo_owner`: Repository owner
- `repo_name`: Repository name
- `status`: Current state
- `created_at`: Creation timestamp
- `updated_at`: Last update timestamp
- `snapshot_image_id`: Associated snapshot ID
- `workspace_path`: Local filesystem path
- `env_vars`: Environment variables
- `pid`: Process ID (if running)

**snapshots table**:
- `id`: Unique identifier
- `sandbox_id`: Associated sandbox ID
- `provider_object_id`: Provider object ID
- `created_at`: Creation timestamp
- `reason`: Reason for snapshot
- `snapshot_path`: Local filesystem path

### Snapshot Management

Snapshots are created:
- After successful prompt completion
- Before sandbox timeout
- On explicit request

Snapshots can be restored to resume sessions:
- Full filesystem restoration
- Environment variables preserved
- Git state preserved

## Security Considerations

### Authentication

- API key authentication for all local manager endpoints
- Bearer token format: `Authorization: Bearer <API_KEY>`
- Control plane authenticates with local manager using API key

### Data Protection

- SQLite database stored locally
- Workspace data stored in configurable directory
- Sensitive environment variables stored in database
- API key should be kept secret and rotated regularly

### Network Security

- Consider running behind a reverse proxy with TLS
- Limit access to the local manager to trusted IPs
- Use VPN for remote access
- Never expose the local manager directly to the internet

## Performance Considerations

### Resource Management

1. **CPU**: Each sandbox runs OpenCode which is CPU-intensive
2. **Memory**: Multiple sandboxes can consume significant RAM
3. **Storage**: Snapshots and workspaces can grow large
4. **Network**: Git clones and package installs require network bandwidth

### Recommendations

1. **Start small**: Begin with 1-2 concurrent sandboxes
2. **Monitor usage**: Track resource consumption
3. **Set appropriate limits**: Adjust `MAX_CONCURRENT` based on available resources
4. **Clean up**: Regularly prune old snapshots and workspaces

## Integration with Electron.js and Desktop Apps

The local sandbox provider is ideal for developing desktop applications:

### Benefits for Electron.js Development

1. **Full environment**: Access to native dependencies
2. **Local builds**: Build and test Electron apps locally
3. **Screenshot capture**: Use agent-browser for UI verification
4. **Testing**: Run full test suites locally

### Example Workflow

```
1. User sends prompt: "Fix the login dialog in our Electron app"
2. Control plane creates local sandbox
3. Sandbox clones the Electron repo
4. OpenCode analyzes the code and makes changes
5. OpenCode runs `npm run build` to build the app
6. OpenCode uses agent-browser to capture screenshots
7. Results are streamed back to the user
8. Sandbox is stopped or snapshot is saved
```

## Troubleshooting

### Common Issues

**Sandbox fails to start**:
- Check that all dependencies are installed (Node.js, OpenCode, sandbox-runtime)
- Verify git is available and configured
- Check network connectivity for git clone

**Control plane cannot reach local manager**:
- Verify local manager is running
- Check firewall settings
- Verify API key is correct
- Check network connectivity between control plane and local machine

**Queue is full**:
- Increase `MAX_CONCURRENT` if more resources are available
- Reduce the number of concurrent sessions
- Implement rate limiting at the client level

**Memory issues**:
- Reduce `MAX_CONCURRENT`
- Implement automatic snapshot cleanup
- Monitor memory usage and alert on high consumption

### Logs

Local sandbox manager logs are printed to stdout:
```
[sandbox] Cloning repository...
[sandbox] Running setup script...
[sandbox] Starting sandbox runtime...
[sandbox] OpenCode server ready
```

## Future Enhancements

Potential improvements for the local sandbox provider:

1. **Multi-machine support**: Distribute sandboxes across multiple local machines
2. **Load balancing**: Route requests to available machines
3. **Auto-scaling**: Dynamically adjust based on load
4. **Distributed snapshots**: Share snapshots across machines
5. **Resource monitoring**: Track and limit resource usage per sandbox
6. **Docker support**: Run sandboxes in containers for better isolation

## Conclusion

The local sandbox provider extends Open-Inspect to run on local hardware, enabling closed-loop development workflows for applications like Electron.js that require local execution. It integrates seamlessly with the existing architecture while providing the flexibility to run sandboxes where they're needed most.