#!/usr/bin/env python3
"""
Local Sandbox Manager - runs on local machines (e.g., Mac Mini) to manage sandbox lifecycle.

This server provides an HTTP API for:
- Creating sandboxes
- Restoring sandboxes from snapshots
- Taking snapshots
- Stopping sandboxes
- Querying sandbox status

It manages:
- Job queueing for concurrent sandbox requests
- State persistence using SQLite
- Sandbox lifecycle management
- Integration with sandbox-runtime
"""

import asyncio
import json
import os
import subprocess
import tempfile
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, String, DateTime, Text, JSON, Integer
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session

# Configuration
API_KEY = os.environ.get("LOCAL_SANDBOX_API_KEY", "local-dev-key")

# Platform-specific data directory - works on Windows, macOS, and Linux
# Use current directory by default for better compatibility
DEFAULT_DATA_DIR = (
    Path(os.environ.get("LOCAL_SANDBOX_DATA_DIR"))
    if os.environ.get("LOCAL_SANDBOX_DATA_DIR")
    else (Path(".") / "sandbox-data")
)
DATA_DIR = DEFAULT_DATA_DIR
MAX_CONCURRENT_SANDBOXES = int(os.environ.get("LOCAL_SANDBOX_MAX_CONCURRENT", "1"))
SANDBOX_TIMEOUT_SECONDS = int(os.environ.get("LOCAL_SANDBOX_TIMEOUT", "7200"))

# Development mode - skips OpenCode startup for testing
DEV_MODE = os.environ.get("LOCAL_SANDBOX_DEV_MODE", "false").lower() == "true"

# Ensure data directories exist
DATA_DIR.mkdir(parents=True, exist_ok=True)
SNAPSHOTS_DIR = DATA_DIR / "snapshots"
SNAPSHOTS_DIR.mkdir(exist_ok=True)
WORKSPACES_DIR = DATA_DIR / "workspaces"
WORKSPACES_DIR.mkdir(exist_ok=True)

print(f"Local Sandbox Manager starting...")
print(f"  Data directory: {DATA_DIR.resolve()}")
print(f"  Max concurrent sandboxes: {MAX_CONCURRENT_SANDBOXES}")
print(f"  Development mode: {DEV_MODE}")

# Database setup
engine = create_engine(f"sqlite:///{DATA_DIR / 'sandboxes.db'}")
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class SandboxDB(Base):
    __tablename__ = "sandboxes"
    
    id = Column(String, primary_key=True, index=True)
    provider_object_id = Column(String, unique=True, index=True)
    session_id = Column(String, index=True)
    sandbox_id = Column(String, index=True)
    repo_owner = Column(String)
    repo_name = Column(String)
    status = Column(String, default="pending")
    created_at = Column(DateTime)
    updated_at = Column(DateTime)
    snapshot_image_id = Column(String)
    workspace_path = Column(String)
    env_vars = Column(JSON)
    pid = Column(Integer, nullable=True)


class SnapshotDB(Base):
    __tablename__ = "snapshots"
    
    id = Column(String, primary_key=True, index=True)
    sandbox_id = Column(String, index=True)
    provider_object_id = Column(String, index=True)
    created_at = Column(DateTime)
    reason = Column(String)
    snapshot_path = Column(String)


Base.metadata.create_all(bind=engine)

# FastAPI app
app = FastAPI(title="Local Sandbox Manager", version="1.0")
security = HTTPBearer()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


async def verify_api_key(credentials: HTTPAuthorizationCredentials = Depends(security)):
    if credentials.credentials != API_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return credentials


class CreateSandboxRequest(BaseModel):
    session_id: str
    sandbox_id: str
    repo_owner: str
    repo_name: str
    control_plane_url: str
    sandbox_auth_token: str
    provider: str
    model: str
    user_env_vars: dict | None = None
    repo_image_id: str | None = None
    repo_image_sha: str | None = None
    timeout_seconds: int = SANDBOX_TIMEOUT_SECONDS
    branch: str | None = None
    code_server_enabled: bool = False
    agent_slack_notify_enabled: bool = False
    mcp_servers: list | None = None
    sandbox_settings: dict | None = None


class RestoreSandboxRequest(BaseModel):
    snapshot_image_id: str
    session_id: str
    sandbox_id: str
    sandbox_auth_token: str
    control_plane_url: str
    repo_owner: str
    repo_name: str
    provider: str
    model: str
    user_env_vars: dict | None = None
    timeout_seconds: int = SANDBOX_TIMEOUT_SECONDS
    branch: str | None = None
    code_server_enabled: bool = False
    agent_slack_notify_enabled: bool = False
    mcp_servers: list | None = None
    sandbox_settings: dict | None = None


class SnapshotRequest(BaseModel):
    provider_object_id: str
    session_id: str
    reason: str


class StopRequest(BaseModel):
    provider_object_id: str
    session_id: str


@dataclass
class SandboxInfo:
    sandbox_id: str
    provider_object_id: str
    status: str
    created_at: float
    code_server_url: str | None = None
    code_server_password: str | None = None
    ttyd_url: str | None = None
    tunnel_urls: dict | None = None


# Job queue for sandbox operations
sandbox_queue = asyncio.Queue(maxsize=100)
active_sandboxes = set()


async def process_queue():
    """Process sandbox creation requests from the queue."""
    while True:
        while len(active_sandboxes) >= MAX_CONCURRENT_SANDBOXES:
            await asyncio.sleep(1)
        
        request = await sandbox_queue.get()
        try:
            await execute_sandbox_creation(request)
        finally:
            sandbox_queue.task_done()


async def execute_sandbox_creation(request: dict):
    """Execute sandbox creation."""
    provider_object_id = request["provider_object_id"]
    active_sandboxes.add(provider_object_id)
    
    try:
        await create_sandbox_internal(request)
    finally:
        active_sandboxes.discard(provider_object_id)


async def create_sandbox_internal(request: dict):
    """Internal sandbox creation logic."""
    db = SessionLocal()
    
    try:
        workspace_path = WORKSPACES_DIR / request["sandbox_id"]
        workspace_path.mkdir(parents=True, exist_ok=True)
        
        env_vars = build_sandbox_env(request)
        
        if DEV_MODE:
            print(f"[DEV MODE] Skipping git clone and runtime startup for sandbox {request['sandbox_id']}")
            await asyncio.sleep(2)
            
            test_file = workspace_path / "test_repo.txt"
            test_file.write_text(f"Test repository for sandbox {request['sandbox_id']}\nCreated: {datetime.now()}")
        else:
            await clone_repo(
                request["repo_owner"],
                request["repo_name"],
                workspace_path,
                request["branch"] or "main",
                env_vars
            )
            
            await run_setup_script(workspace_path, env_vars)
            
            await start_sandbox_runtime(workspace_path, env_vars)
        
        db_sandbox = SandboxDB(
            id=str(uuid.uuid4()),
            provider_object_id=request["provider_object_id"],
            session_id=request["session_id"],
            sandbox_id=request["sandbox_id"],
            repo_owner=request["repo_owner"],
            repo_name=request["repo_name"],
            status="running",
            created_at=datetime.now(),
            updated_at=datetime.now(),
            workspace_path=str(workspace_path),
            env_vars=env_vars,
        )
        db.add(db_sandbox)
        db.commit()
        
        print(f"Sandbox created: {request['sandbox_id']}")
    finally:
        db.close()


def build_sandbox_env(request: dict) -> dict:
    """Build environment variables for the sandbox."""
    env = os.environ.copy()
    env.update({
        "SANDBOX_ID": request["sandbox_id"],
        "CONTROL_PLANE_URL": request["control_plane_url"],
        "SANDBOX_AUTH_TOKEN": request["sandbox_auth_token"],
        "REPO_OWNER": request["repo_owner"],
        "REPO_NAME": request["repo_name"],
        "SESSION_CONFIG": json.dumps({
            "session_id": request["session_id"],
            "branch": request["branch"] or "main",
            "provider": request["provider"],
            "model": request["model"],
        }),
        "HOME": "/root",
        "NODE_ENV": "development",
    })
    
    if request.get("user_env_vars"):
        env.update(request["user_env_vars"])
    
    if request.get("code_server_enabled"):
        env["CODE_SERVER_PASSWORD"] = generate_code_server_password(request["sandbox_id"])
    
    return env


def generate_code_server_password(sandbox_id: str) -> str:
    """Generate a secure password for code-server."""
    import hashlib
    return hashlib.sha256(f"code-server-{sandbox_id}".encode()).hexdigest()[:32]


async def clone_repo(repo_owner: str, repo_name: str, workspace_path: Path, branch: str, env: dict):
    """Clone the repository into the workspace."""
    repo_url = f"https://github.com/{repo_owner}/{repo_name}.git"
    
    result = await asyncio.create_subprocess_exec(
        "git",
        "clone",
        "--depth", "100",
        "--branch", branch,
        repo_url,
        str(workspace_path),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )
    
    stdout, stderr = await result.communicate()
    
    if result.returncode != 0:
        raise RuntimeError(f"Git clone failed: {stderr.decode()}")


async def run_setup_script(workspace_path: Path, env: dict):
    """Run .openinspect/setup.sh if it exists."""
    setup_script = workspace_path / ".openinspect" / "setup.sh"
    if not setup_script.exists():
        return
    
    result = await asyncio.create_subprocess_exec(
        "bash",
        str(setup_script),
        cwd=workspace_path,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )
    
    stdout, stderr = await result.communicate()
    
    if result.returncode != 0:
        print(f"Setup script failed (non-fatal): {stderr.decode()}")


async def start_sandbox_runtime(workspace_path: Path, env: dict):
    """Start the sandbox runtime process."""
    proc = await asyncio.create_subprocess_exec(
        "python",
        "-m",
        "sandbox_runtime.entrypoint",
        cwd=workspace_path,
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    
    async def log_output():
        while True:
            line = await proc.stdout.readline()
            if not line:
                break
            print(f"[sandbox] {line.decode().strip()}")
    
    asyncio.create_task(log_output())


@app.post("/create-sandbox")
async def create_sandbox(
    request: CreateSandboxRequest,
    credentials: HTTPAuthorizationCredentials = Depends(verify_api_key),
    db: Session = Depends(get_db)
):
    provider_object_id = str(uuid.uuid4())
    
    await sandbox_queue.put({
        "provider_object_id": provider_object_id,
        "session_id": request.session_id,
        "sandbox_id": request.sandbox_id,
        "repo_owner": request.repo_owner,
        "repo_name": request.repo_name,
        "control_plane_url": request.control_plane_url,
        "sandbox_auth_token": request.sandbox_auth_token,
        "provider": request.provider,
        "model": request.model,
        "user_env_vars": request.user_env_vars,
        "branch": request.branch,
        "code_server_enabled": request.code_server_enabled,
        "agent_slack_notify_enabled": request.agent_slack_notify_enabled,
    })
    
    return {
        "success": True,
        "data": {
            "sandbox_id": request.sandbox_id,
            "provider_object_id": provider_object_id,
            "status": "spawning",
            "created_at": datetime.now().timestamp(),
        },
    }


@app.post("/restore-sandbox")
async def restore_sandbox(
    request: RestoreSandboxRequest,
    credentials: HTTPAuthorizationCredentials = Depends(verify_api_key),
    db: Session = Depends(get_db)
):
    snapshot = db.query(SnapshotDB).filter(SnapshotDB.id == request.snapshot_image_id).first()
    
    if not snapshot:
        raise HTTPException(status_code=404, detail="Snapshot not found")
    
    provider_object_id = str(uuid.uuid4())
    
    workspace_path = WORKSPACES_DIR / request.sandbox_id
    workspace_path.mkdir(parents=True, exist_ok=True)
    
    await restore_snapshot(snapshot.snapshot_path, workspace_path)
    
    env_vars = build_sandbox_env({
        "sandbox_id": request.sandbox_id,
        "control_plane_url": request.control_plane_url,
        "sandbox_auth_token": request.sandbox_auth_token,
        "repo_owner": request.repo_owner,
        "repo_name": request.repo_name,
        "session_id": request.session_id,
        "branch": request.branch,
        "provider": request.provider,
        "model": request.model,
        "user_env_vars": request.user_env_vars,
        "code_server_enabled": request.code_server_enabled,
    })
    
    await run_start_script(workspace_path, env_vars)
    await start_sandbox_runtime(workspace_path, env_vars)
    
    db_sandbox = SandboxDB(
        id=str(uuid.uuid4()),
        provider_object_id=provider_object_id,
        session_id=request.session_id,
        sandbox_id=request.sandbox_id,
        repo_owner=request.repo_owner,
        repo_name=request.repo_name,
        status="running",
        created_at=datetime.now(),
        updated_at=datetime.now(),
        workspace_path=str(workspace_path),
        snapshot_image_id=request.snapshot_image_id,
        env_vars=env_vars,
    )
    db.add(db_sandbox)
    db.commit()
    
    return {
        "success": True,
        "data": {
            "sandbox_id": request.sandbox_id,
            "provider_object_id": provider_object_id,
            "status": "running",
            "created_at": datetime.now().timestamp(),
        },
    }


async def restore_snapshot(snapshot_path: str, workspace_path: Path):
    """Restore a snapshot to the workspace."""
    import shutil
    shutil.rmtree(workspace_path, ignore_errors=True)
    shutil.copytree(snapshot_path, workspace_path)


async def run_start_script(workspace_path: Path, env: dict):
    """Run .openinspect/start.sh if it exists."""
    start_script = workspace_path / ".openinspect" / "start.sh"
    if not start_script.exists():
        return
    
    result = await asyncio.create_subprocess_exec(
        "bash",
        str(start_script),
        cwd=workspace_path,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )
    
    stdout, stderr = await result.communicate()
    
    if result.returncode != 0:
        raise RuntimeError(f"Start script failed: {stderr.decode()}")


@app.post("/snapshot-sandbox")
async def snapshot_sandbox(
    request: SnapshotRequest,
    credentials: HTTPAuthorizationCredentials = Depends(verify_api_key),
    db: Session = Depends(get_db)
):
    sandbox = db.query(SandboxDB).filter(
        SandboxDB.provider_object_id == request.provider_object_id
    ).first()
    
    if not sandbox:
        raise HTTPException(status_code=404, detail="Sandbox not found")
    
    snapshot_id = str(uuid.uuid4())
    snapshot_path = SNAPSHOTS_DIR / snapshot_id
    snapshot_path.mkdir(parents=True, exist_ok=True)
    
    await take_snapshot(sandbox.workspace_path, str(snapshot_path))
    
    db_snapshot = SnapshotDB(
        id=snapshot_id,
        sandbox_id=sandbox.sandbox_id,
        provider_object_id=sandbox.provider_object_id,
        created_at=datetime.now(),
        reason=request.reason,
        snapshot_path=str(snapshot_path),
    )
    db.add(db_snapshot)
    db.commit()
    
    sandbox.snapshot_image_id = snapshot_id
    db.commit()
    
    return {"success": True, "data": {"image_id": snapshot_id}}


async def take_snapshot(source_path: str, destination_path: str):
    """Create a snapshot of the workspace."""
    import shutil
    import os
    
    dest_path = Path(destination_path)
    if dest_path.exists():
        shutil.rmtree(dest_path)
    
    shutil.copytree(source_path, destination_path)


@app.post("/stop-sandbox")
async def stop_sandbox(
    request: StopRequest,
    credentials: HTTPAuthorizationCredentials = Depends(verify_api_key),
    db: Session = Depends(get_db)
):
    sandbox = db.query(SandboxDB).filter(
        SandboxDB.provider_object_id == request.provider_object_id
    ).first()
    
    if not sandbox:
        raise HTTPException(status_code=404, detail="Sandbox not found")
    
    if sandbox.pid:
        try:
            os.kill(sandbox.pid, 9)
        except ProcessLookupError:
            pass
    
    sandbox.status = "stopped"
    sandbox.updated_at = datetime.now()
    db.commit()
    
    active_sandboxes.discard(request.provider_object_id)
    
    return {"success": True}


@app.get("/sandbox-status/{provider_object_id}")
async def get_sandbox_status(
    provider_object_id: str,
    credentials: HTTPAuthorizationCredentials = Depends(verify_api_key),
    db: Session = Depends(get_db)
):
    sandbox = db.query(SandboxDB).filter(
        SandboxDB.provider_object_id == provider_object_id
    ).first()
    
    if not sandbox:
        return {"status": "unknown"}
    
    return {"status": sandbox.status}


@app.get("/")
async def root():
    return {
        "service": "Local Sandbox Manager",
        "version": "1.0",
        "status": "running",
        "endpoints": {
            "health": "/health",
            "create-sandbox": "/create-sandbox (POST)",
            "restore-sandbox": "/restore-sandbox (POST)",
            "snapshot-sandbox": "/snapshot-sandbox (POST)",
            "stop-sandbox": "/stop-sandbox (POST)",
            "sandbox-status": "/sandbox-status/{provider_object_id} (GET)",
            "list-sandboxes": "/list-sandboxes (GET)",
        },
        "notes": "All endpoints except / and /health require Authorization header with Bearer token",
    }


@app.get("/health")
async def health():
    return {"status": "healthy", "active_sandboxes": len(active_sandboxes)}


@app.get("/list-sandboxes")
async def list_sandboxes(
    credentials: HTTPAuthorizationCredentials = Depends(verify_api_key),
    db: Session = Depends(get_db)
):
    sandboxes = db.query(SandboxDB).all()
    return {
        "sandboxes": [
            {
                "sandbox_id": sb.sandbox_id,
                "provider_object_id": sb.provider_object_id,
                "status": sb.status,
                "created_at": sb.created_at.timestamp() if sb.created_at else None,
            }
            for sb in sandboxes
        ]
    }


@app.delete("/cleanup-sandboxes")
async def cleanup_sandboxes(
    credentials: HTTPAuthorizationCredentials = Depends(verify_api_key),
    db: Session = Depends(get_db)
):
    import shutil
    
    sandboxes = db.query(SandboxDB).all()
    deleted_count = 0
    
    for sb in sandboxes:
        if sb.workspace_path:
            try:
                shutil.rmtree(sb.workspace_path, ignore_errors=True)
            except Exception:
                pass
        db.delete(sb)
        deleted_count += 1
    
    snapshots = db.query(SnapshotDB).all()
    for snap in snapshots:
        if snap.snapshot_path:
            try:
                shutil.rmtree(snap.snapshot_path, ignore_errors=True)
            except Exception:
                pass
        db.delete(snap)
    
    db.commit()
    
    return {"success": True, "deleted_sandboxes": deleted_count}


@app.on_event("startup")
async def startup_event():
    asyncio.create_task(process_queue())


if __name__ == "__main__":
    port = int(os.environ.get("LOCAL_SANDBOX_PORT", "8788"))
    uvicorn.run(app, host="127.0.0.1", port=port)