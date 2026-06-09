# Local Sandbox Provider - Features & Architecture

## Overview

This document describes the improvements, features, and optimizations implemented for the Local Sandbox Provider, as well as how it manages lifecycle, queueing, state persistence, and coexistence with the original Modal infrastructure.

---

## 1. Improvements, Features & Optimizations

### Core Features Implemented

| Feature | Description | Implementation File |
|---------|-------------|---------------------|
| **Local Sandbox Provider** | Run sandboxes on local machines (Mac Mini, PC, etc.) instead of Modal | [provider.ts](file:///C:/Git/Altar/Background Agent/packages/control-plane/src/sandbox/providers/local/provider.ts) |
| **Local Sandbox Manager** | FastAPI server managing sandbox lifecycle | [main.py](file:///C:/Git/Altar/Background Agent/packages/local-infra/src/main.py) |
| **Job Queueing System** | Concurrent request management with configurable limits | [main.py#L190-L209](file:///C:/Git/Altar/Background Agent/packages/local-infra/src/main.py#L190-L209) |
| **State Persistence** | SQLite database for sandbox and snapshot metadata | [main.py#L65-L101](file:///C:/Git/Altar/Background Agent/packages/local-infra/src/main.py#L65-L101) |
| **Snapshot Management** | Create and restore filesystem snapshots | [main.py#L488-L533](file:///C:/Git/Altar/Background Agent/packages/local-infra/src/main.py#L488-L533) |
| **API Authentication** | API key protection for all endpoints | [main.py#L116-L119](file:///C:/Git/Altar/Background Agent/packages/local-infra/src/main.py#L116-L119) |
| **Development Mode** | Skip git clone and runtime for testing | [main.py#L51](file:///C:/Git/Altar/Background Agent/packages/local-infra/src/main.py#L51) |

### Architectural Optimizations

#### Pluggable Design
The local provider follows the existing provider pattern established by Modal, Daytona, and Vercel providers, ensuring seamless integration with the control plane.

#### Platform Compatibility
- Works on Windows, macOS (Intel/M1/M2/M3), and Linux
- Uses platform-appropriate data directories
- Handles path separators correctly across platforms

#### Resource Management
- Configurable concurrent sandbox limit (default: 1)
- Queue depth limiting (max: 100 pending requests)
- Backpressure handling to prevent resource exhaustion

#### Graceful Degradation
- Development mode allows testing without full OpenCode infrastructure
- All API endpoints work normally in development mode

### Additional Feature Ideas

1. **Multi-Machine Support**: Distribute sandboxes across multiple local machines
2. **Load Balancing**: Route requests to available machines based on load
3. **Auto-scaling**: Dynamically adjust concurrent sandboxes based on resource usage
4. **Resource Monitoring**: Track CPU, memory, and storage usage per sandbox
5. **Docker Support**: Run sandboxes in containers for better isolation
6. **Distributed Snapshots**: Share snapshots across multiple machines
7. **Web Dashboard**: Visual interface for monitoring and management

---

## 2. Lifecycle, Queueing, State Management & Coexistence

### Sandbox Lifecycle Management

#### State Machine

```
pending → spawning → connecting → running → stopped
                              ↘ failed
                              ↘ stale
```

#### State Transitions

| State | Description |
|-------|-------------|
| **pending** | Initial state before spawn request |
| **spawning** | Sandbox creation in progress |
| **connecting** | Sandbox created, waiting for bridge connection |
| **running** | Sandbox active and ready to receive prompts |
| **stopped** | Sandbox stopped due to inactivity timeout |
| **failed** | Sandbox failed to start or encountered error |
| **stale** | Sandbox heartbeat timed out |

#### Timeouts

| Timeout | Description | Default |
|---------|-------------|---------|
| Connecting | Wait for bridge connection | 30 seconds |
| Heartbeat | Wait for heartbeat before marking stale | 60 seconds |
| Inactivity | Wait before stopping idle sandbox | 2 hours |

### Job Queueing System

#### Implementation

```python
# Queue with max 100 pending requests
sandbox_queue = asyncio.Queue(maxsize=100)

# Track active sandboxes
active_sandboxes = set()

async def process_queue():
    while True:
        request = await sandbox_queue.get()
        # Enforce concurrency limit
        if len(active_sandboxes) >= MAX_CONCURRENT_SANDBOXES:
            await asyncio.sleep(1)
            sandbox_queue.put(request)
            continue
        asyncio.create_task(execute_sandbox_creation(request))
```

#### Queue Behavior

1. Requests are added to queue when received
2. Worker processes dequeue when capacity is available
3. If queue is full (100 items), new requests are rejected
4. Active sandboxes tracked to enforce concurrency limits
5. FIFO ordering ensures fair scheduling

### State Persistence

#### Database Schema

**sandboxes table**:

| Column | Type | Description |
|--------|------|-------------|
| id | String | Unique identifier |
| provider_object_id | String | Local manager sandbox ID |
| session_id | String | Control plane session ID |
| sandbox_id | String | Logical sandbox ID |
| repo_owner | String | Repository owner |
| repo_name | String | Repository name |
| status | String | Current state (running/stopped/failed) |
| created_at | DateTime | Creation timestamp |
| updated_at | DateTime | Last update timestamp |
| workspace_path | String | Local filesystem path |
| env_vars | JSON | Environment variables |
| pid | Integer | Process ID (if running) |

**snapshots table**:

| Column | Type | Description |
|--------|------|-------------|
| id | String | Unique identifier |
| sandbox_id | String | Associated sandbox ID |
| provider_object_id | String | Provider object ID |
| created_at | DateTime | Creation timestamp |
| reason | String | Reason for snapshot |
| snapshot_path | String | Local filesystem path |

#### Snapshot Management

Snapshots are created:
- After successful prompt completion
- Before sandbox timeout
- On explicit request

Snapshots can be restored to resume sessions:
- Full filesystem restoration
- Environment variables preserved
- Git state preserved

### Coexistence with Modal Infrastructure

#### Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    Control Plane (Cloudflare)              │
│  ┌──────────────────────────────────────────────────────┐  │
│  │           SandboxLifecycleManager                    │  │
│  │   ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐   │  │
│  │   │  Modal  │ │ Daytona │ │ Vercel  │ │  Local  │   │  │
│  │   └────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘   │  │
│  └────────┼───────────┼───────────┼───────────┼────────┘  │
└───────────┼───────────┼───────────┼───────────┼───────────┘
            │           │           │           │ HTTP API
            ▼           ▼           ▼           ▼
       Modal Cloud   Daytona    Vercel    Local Machine
                                        (Mac Mini/PC)
```

#### Coexistence Strategy

| Aspect | Implementation |
|--------|---------------|
| **Provider Selection** | `SANDBOX_PROVIDER` environment variable |
| **Session State** | Stored in Cloudflare Durable Objects |
| **API Interface** | All providers use identical API |
| **Snapshot Storage** | Local provider stores locally |
| **Load Balancing** | Switch providers per-session |
| **Fault Tolerance** | Fallback to other providers if local fails |

#### Configuration

**Control Plane (Cloudflare)**:
```bash
SANDBOX_PROVIDER=local
LOCAL_SANDBOX_MANAGER_URL=http://your-mac-mini.local:8788
LOCAL_SANDBOX_API_KEY=your-secure-key
```

**Local Manager**:
```bash
LOCAL_SANDBOX_API_KEY=your-secure-key
LOCAL_SANDBOX_MAX_CONCURRENT=3
LOCAL_SANDBOX_DEV_MODE=false
LOCAL_SANDBOX_DATA_DIR=/var/local-sandboxes
```

---

## Setup Instructions

### Prerequisites

1. **Local Machine**: Python 3.10+, Node.js 22+, Git
2. **Control Plane**: Cloudflare Workers deployment

### Installation

```bash
# Install local sandbox manager
cd packages/local-infra
pip install -e .

# Start the manager
export LOCAL_SANDBOX_API_KEY="your-key"
export LOCAL_SANDBOX_MAX_CONCURRENT="3"
python -m local_sandbox_manager.main
```

### Testing

```bash
# Run test script
python test_local_sandbox.py
```

### API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Service status and endpoint list |
| `/health` | GET | Health check |
| `/create-sandbox` | POST | Create new sandbox |
| `/restore-sandbox` | POST | Restore from snapshot |
| `/snapshot-sandbox` | POST | Create snapshot |
| `/stop-sandbox` | POST | Stop sandbox |
| `/sandbox-status/{id}` | GET | Get sandbox status |
| `/list-sandboxes` | GET | List all sandboxes |

---

## Benefits

### For Development Workflows
- Lower latency for local development
- Full closed-loop build/run/test/screenshot/eval
- Works with private repositories
- Access to local hardware

### For Electron.js Development
- Full environment access (native dependencies)
- Local builds and testing
- Screenshot capture for UI verification
- Complete test suite execution

### For Cost Savings
- Reduced cloud provider costs
- Use existing hardware
- Scale based on available resources

---

## Future Enhancements

1. **Multi-Machine Cluster**: Manage sandboxes across multiple local machines
2. **Advanced Load Balancing**: Intelligent routing based on resource usage
3. **Auto-scaling**: Dynamically adjust capacity
4. **Docker Containerization**: Better isolation and reproducibility
5. **Web Management Dashboard**: Visual monitoring and control
6. **Distributed Snapshot Storage**: Shared snapshot repository
7. **Resource Quotas**: Per-user/per-team resource limits
8. **Audit Logs**: Track all sandbox operations
9. **Alerting**: Notify on errors and resource thresholds
10. **CLI Tool**: Command-line interface for management

---

## Conclusion

The Local Sandbox Provider extends Open-Inspect to run sandboxes on local hardware, enabling closed-loop development workflows while maintaining full compatibility with the existing Modal-based infrastructure. The implementation follows the existing architecture patterns and provides a robust foundation for future enhancements.