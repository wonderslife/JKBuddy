"""
Code Command - Self-Hosted Code Interpreter for AI Agents
==========================================================
A drop-in replacement for LibreChat's code interpreter (code.librechat.ai)
Features:
- Secure Docker sandboxing (no network, memory limits, timeouts)
- PowerPoint, charts, mind maps generation
Setup:
1. Build sandbox: docker build -t code-sandbox:latest .
2. Install deps: pip install fastapi uvicorn docker pydantic
3. Run: python code_interpreter.py --port 8095
4. Configure your AI agent with the API URL
API compatible with LibreChat's @librechat/agents CodeExecutor format.
"""
import asyncio
import os
import sys
import uuid
import json
import logging
import shutil
import re
import time
import threading
import secrets
import string
from pathlib import Path
from typing import Dict, List, Optional, Any
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Header, File, UploadFile, Request
from fastapi.responses import StreamingResponse, JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn
# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("code-command")
# Session storage
sessions: Dict[str, Dict[str, Any]] = {}
# Default API key
DEFAULT_API_KEY = os.getenv("CODE_API_KEY", "code-command-dev-key")
# Security warnings
if not DEFAULT_API_KEY:
    logger.warning("WARNING: CODE_API_KEY is empty - authentication is DISABLED!")
elif DEFAULT_API_KEY == "code-command-dev-key":
    logger.warning("WARNING: Using default API key. Set CODE_API_KEY env var for production!")
# Work directory for code execution
WORK_DIR = os.getenv("CODE_WORK_DIR", "/tmp/code_command")
os.makedirs(WORK_DIR, exist_ok=True)
# Shared assets directory (icons, templates, helpers) - mounted read-only in containers
SHARED_ASSETS_PATH = os.getenv("SHARED_ASSETS_PATH", str(Path(__file__).parent / "shared_assets"))
# Session cleanup settings
SESSION_MAX_AGE_HOURS = int(os.getenv("SESSION_MAX_AGE_HOURS", 24))
CLEANUP_INTERVAL_MINUTES = int(os.getenv("CLEANUP_INTERVAL_MINUTES", 60))
# Docker image name for sandbox
SANDBOX_IMAGE = os.getenv("SANDBOX_IMAGE", "code-sandbox:latest")
# CPU limit (in CPUs, e.g., 0.5 = half a CPU core)
CPU_LIMIT = float(os.getenv("CPU_LIMIT", 0.5))
# Workspace size limit in bytes (default 100MB)
WORKSPACE_SIZE_LIMIT = int(os.getenv("WORKSPACE_SIZE_LIMIT", 100 * 1024 * 1024))
# Execution timeout (default 120 seconds for complex data analysis)
CODE_EXEC_TIMEOUT = int(os.getenv("CODE_EXEC_TIMEOUT", 120))
# Nanoid alphabet (URL-safe characters)
NANOID_ALPHABET = string.ascii_letters + string.digits + '_-'
def generate_id(size: int = 21) -> str:
    """Generate a nanoid-style ID (21 chars, URL-safe).
    LibreChat expects IDs in this format for file downloads.
    Using secrets module for cryptographic randomness.
    """
    return ''.join(secrets.choice(NANOID_ALPHABET) for _ in range(size))
def get_directory_size(path: str) -> int:
    """Get total size of a directory in bytes"""
    total = 0
    for dirpath, dirnames, filenames in os.walk(path):
        for filename in filenames:
            filepath = os.path.join(dirpath, filename)
            try:
                total += os.path.getsize(filepath)
            except (OSError, FileNotFoundError):
                pass
    return total
class ExecuteRequest(BaseModel):
    """Code execution request matching @librechat/agents format"""
    lang: str = "python"
    code: str
    session_id: Optional[str] = None
    args: Optional[Dict[str, Any]] = None
    files: Optional[List[Dict[str, str]]] = None
class ExecuteResponse(BaseModel):
    """Code execution response matching @librechat/agents format"""
    stdout: str = ""
    stderr: str = ""
    files: List[Dict[str, str]] = []
    session_id: str
class FileInfo(BaseModel):
    """File information"""
    name: str
    size: int
    type: str = "file"
def verify_api_key(x_api_key: Optional[str] = None) -> bool:
    """Verify API key"""
    if not DEFAULT_API_KEY:
        return True
    return x_api_key == DEFAULT_API_KEY
def validate_session_id(session_id: str) -> bool:
    """Validate session_id is safe (UUID or alphanumeric with hyphens/underscores)"""
    return bool(re.match(r'^[a-zA-Z0-9_-]+$', session_id))
def get_or_create_session(session_id: Optional[str] = None) -> str:
    """Get existing session or create new one"""
    if session_id:
        if not validate_session_id(session_id):
            raise ValueError(f"Invalid session_id: {session_id}")
        if session_id in sessions:
            return session_id
    new_session_id = session_id or generate_id()
    workspace = os.path.join(WORK_DIR, new_session_id)
    os.makedirs(workspace, exist_ok=True)
    # Make workspace world-writable so sandbox container (non-root user) can write output files
    os.chmod(workspace, 0o777)
    sessions[new_session_id] = {
        "workspace": workspace,
        "files": {},  # file_id -> {name, path}
        "results": {},  # file_id -> {name, path}
        "created_at": time.time(),  # For cleanup
    }
    return new_session_id
def execute_bash_code(code: str, workspace: str) -> tuple[str, str, List[Dict[str, str]]]:
    """在 Docker 沙箱中执行 bash 脚本。
    兼容 LibreChat 内部用 lang='bash' 驱动的 read_file / write_file 等工具。
    /mnt/data 已通过镜像内的软链指向 /workspace，无需额外挂载。
    """
    import docker
    script_path = os.path.join(workspace, "_exec.sh")
    with open(script_path, 'w') as f:
        f.write(code)
        f.flush()
        os.fsync(f.fileno())
    stdout = ""
    stderr = ""
    try:
        client = docker.from_env()
        volumes = {
            workspace: {"bind": "/workspace", "mode": "rw"},
        }
        if os.path.exists(SHARED_ASSETS_PATH):
            volumes[SHARED_ASSETS_PATH] = {"bind": "/mnt/shared", "mode": "ro"}
        container = client.containers.run(
            image=SANDBOX_IMAGE,
            command=["bash", "/workspace/_exec.sh"],
            volumes=volumes,
            working_dir="/workspace",
            network_mode="none",
            mem_limit="256m",
            memswap_limit="256m",
            pids_limit=50,
            nano_cpus=int(CPU_LIMIT * 1e9),
            read_only=True,
            security_opt=["no-new-privileges"],
            tmpfs={"/tmp": "size=64m"},
            detach=True,
            stdout=True,
            stderr=True,
        )
        try:
            result = container.wait(timeout=CODE_EXEC_TIMEOUT)
            stdout = container.logs(stdout=True, stderr=False).decode('utf-8')
            stderr = container.logs(stdout=False, stderr=True).decode('utf-8')
        except Exception as timeout_err:
            stderr = f"Execution timed out after {CODE_EXEC_TIMEOUT} seconds"
            try:
                container.kill()
            except:
                pass
        finally:
            try:
                container.remove(force=True)
            except:
                pass
    except docker.errors.ContainerError as e:
        stderr = e.stderr.decode('utf-8') if e.stderr else str(e)
    except docker.errors.ImageNotFound:
        stderr = f"Docker image '{SANDBOX_IMAGE}' not found. Run: docker build -t {SANDBOX_IMAGE} ."
    except docker.errors.APIError as e:
        stderr = f"Docker API error: {str(e)}"
    except Exception as e:
        stderr = f"Execution error: {str(e)}"
    finally:
        if os.path.exists(script_path):
            os.remove(script_path)
    # 收集新生成的文件（排除隐藏文件、脚本和缓存）
    output_files = []
    excluded_prefixes = ('_', '.', 'fontlist', 'matplotlib-')
    for item in os.listdir(workspace):
        if item.startswith(excluded_prefixes):
            continue
        file_path = os.path.join(workspace, item)
        if os.path.isfile(file_path):
            file_id = generate_id()
            output_files.append({"name": item, "id": file_id})
    return stdout, stderr, output_files
def execute_python_code(code: str, workspace: str) -> tuple[str, str, List[Dict[str, str]]]:
    """
    Execute Python code in a Docker sandbox.
    Security measures:
    - network_mode="none" - No network access
    - mem_limit="256m" - Max 256MB RAM
    - pids_limit=50 - Prevent fork bombs
    - read_only=True - Read-only root filesystem
    - /workspace mounted read-write for output files
    - timeout - Execution time limit
    Returns (stdout, stderr, output_files)
    """
    import docker
    # Create script file in workspace
    script_path = os.path.join(workspace, "_exec.py")
    with open(script_path, 'w') as f:
        f.write(code)
        f.flush()
        os.fsync(f.fileno())
    # Debug: verify file exists and log
    if not os.path.exists(script_path):
        logger.error(f"Script file not created at {script_path}")
        return "", f"Failed to create script file at {script_path}", []
    else:
        logger.info(f"Script file created at {script_path}, size={os.path.getsize(script_path)}")
    stdout = ""
    stderr = ""
    try:
        client = docker.from_env()
        # Build volume mounts
        volumes = {
            workspace: {"bind": "/workspace", "mode": "rw"},
        }
        # Mount shared assets if available
        if os.path.exists(SHARED_ASSETS_PATH):
            volumes[SHARED_ASSETS_PATH] = {"bind": "/mnt/shared", "mode": "ro"}
        # Run in sandboxed container
        # We run detached so we can enforce our own timeout (container.wait has timeout param)
        # Security flags explained:
        #   network_mode="none" - Prevents data exfiltration and external calls
        #   mem_limit - Prevents memory exhaustion attacks
        #   pids_limit - Prevents fork bombs
        #   read_only - Prevents writing to system files (workspace is mounted rw)
        #   no-new-privileges - Prevents privilege escalation exploits
        container = client.containers.run(
            image=SANDBOX_IMAGE,
            command=["python", "/workspace/_exec.py"],
            volumes=volumes,
            working_dir="/workspace",
            network_mode="none",
            mem_limit="256m",
            memswap_limit="256m",
            pids_limit=50,
            nano_cpus=int(CPU_LIMIT * 1e9),
            read_only=True,
            security_opt=["no-new-privileges"],
            tmpfs={"/tmp": "size=64m"},  # Writable temp dir for matplotlib cache etc
            detach=True,
            stdout=True,
            stderr=True,
        )
        try:
            # Wait for container with timeout
            result = container.wait(timeout=CODE_EXEC_TIMEOUT)
            stdout = container.logs(stdout=True, stderr=False).decode('utf-8')
            stderr = container.logs(stdout=False, stderr=True).decode('utf-8')
        except Exception as timeout_err:
            stderr = f"Execution timed out after {CODE_EXEC_TIMEOUT} seconds"
            try:
                container.kill()
            except:
                pass
        finally:
            try:
                container.remove(force=True)
            except:
                pass
    except docker.errors.ContainerError as e:
        stderr = e.stderr.decode('utf-8') if e.stderr else str(e)
    except docker.errors.ImageNotFound:
        stderr = f"Docker image '{SANDBOX_IMAGE}' not found. Run: docker build -t {SANDBOX_IMAGE} ."
    except docker.errors.APIError as e:
        stderr = f"Docker API error: {str(e)}"
    except Exception as e:
        stderr = f"Execution error: {str(e)}"
    finally:
        # Clean up script file
        if os.path.exists(script_path):
            os.remove(script_path)
    # Check workspace size limit
    workspace_size = get_directory_size(workspace)
    if workspace_size > WORKSPACE_SIZE_LIMIT:
        size_mb = workspace_size / (1024 * 1024)
        limit_mb = WORKSPACE_SIZE_LIMIT / (1024 * 1024)
        stderr += f"\nWorkspace size ({size_mb:.1f}MB) exceeds limit ({limit_mb:.1f}MB). Some files may be removed."
        logger.warning(f"Workspace size limit exceeded: {size_mb:.1f}MB > {limit_mb:.1f}MB")
    # Find any new files created (excluding hidden files, scripts, and cache files)
    output_files = []
    excluded_prefixes = ('_', '.', 'fontlist', 'matplotlib-')
    for item in os.listdir(workspace):
        if item.startswith(excluded_prefixes):
            continue
        file_path = os.path.join(workspace, item)
        if os.path.isfile(file_path):
            file_id = generate_id()
            output_files.append({
                "name": item,
                "id": file_id
            })
    return stdout, stderr, output_files
def cleanup_old_sessions():
    """Remove sessions older than SESSION_MAX_AGE_HOURS"""
    max_age_seconds = SESSION_MAX_AGE_HOURS * 3600
    current_time = time.time()
    sessions_to_delete = []
    for session_id, session_data in sessions.items():
        created_at = session_data.get("created_at", current_time)
        if current_time - created_at > max_age_seconds:
            sessions_to_delete.append(session_id)
    for session_id in sessions_to_delete:
        try:
            workspace = sessions[session_id].get("workspace")
            if workspace and os.path.exists(workspace):
                shutil.rmtree(workspace)
            del sessions[session_id]
            logger.info(f"Cleaned up old session: {session_id}")
        except Exception as e:
            logger.error(f"Error cleaning up session {session_id}: {e}")
    # Also clean up orphaned workspace directories
    try:
        for item in os.listdir(WORK_DIR):
            item_path = os.path.join(WORK_DIR, item)
            if os.path.isdir(item_path):
                # Check if directory is old
                dir_mtime = os.path.getmtime(item_path)
                if current_time - dir_mtime > max_age_seconds:
                    if item not in sessions:
                        shutil.rmtree(item_path)
                        logger.info(f"Cleaned up orphaned workspace: {item}")
    except Exception as e:
        logger.error(f"Error cleaning up orphaned workspaces: {e}")
    return len(sessions_to_delete)
def cleanup_worker():
    """Background thread that periodically cleans up old sessions"""
    while True:
        time.sleep(CLEANUP_INTERVAL_MINUTES * 60)
        try:
            session_count = cleanup_old_sessions()
            if session_count > 0:
                logger.info(f"Cleanup completed: {session_count} sessions removed")
        except Exception as e:
            logger.error(f"Cleanup worker error: {e}")
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events"""
    logger.info("Starting Code Command API...")
    logger.info(f"Work directory: {WORK_DIR}")
    logger.info(f"Shared assets: {SHARED_ASSETS_PATH}")
    logger.info(f"Session cleanup: every {CLEANUP_INTERVAL_MINUTES}min, max age {SESSION_MAX_AGE_HOURS}h")
    # Start cleanup worker thread
    cleanup_thread = threading.Thread(target=cleanup_worker, daemon=True)
    cleanup_thread.start()
    logger.info("Cleanup worker started")
    yield
    # Cleanup on shutdown
    logger.info("Shutting down Code Command API...")
app = FastAPI(
    title="Code Command API",
    description="Self-hosted code interpreter for AI agents. Drop-in replacement for LibreChat's code.librechat.ai",
    version="1.0.0",
    lifespan=lifespan
)
# CORS origins - restrict to specific hosts (configurable via env)
ALLOWED_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:3080,http://localhost:3000").split(",")
# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
@app.get("/health")
async def health():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "code-command",
        "version": "1.0.0"
    }
@app.post("/exec")
async def execute_code(
    request: ExecuteRequest,
    x_api_key: Optional[str] = Header(None, alias="X-API-Key")
) -> ExecuteResponse:
    """
    Execute code in a sandboxed environment.
    Matches @librechat/agents CodeExecutor API format.
    """
    if not verify_api_key(x_api_key):
        raise HTTPException(status_code=401, detail="Invalid API key")
    # Get or create session
    try:
        session_id = get_or_create_session(request.session_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    session = sessions[session_id]
    workspace = session["workspace"]
    logger.info(f"Executing {request.lang} code in session {session_id}")
    # Execute based on language
    if request.lang.lower() in ["python", "py", "python3"]:
        stdout, stderr, output_files = execute_python_code(request.code, workspace)
    elif request.lang.lower() in ["bash", "sh", "shell"]:
        stdout, stderr, output_files = execute_bash_code(request.code, workspace)
    else:
        # For now, only Python and bash are supported
        stdout = ""
        stderr = f"Language '{request.lang}' is not yet supported. Currently only Python and bash are available."
        output_files = []
    # Store output files in session
    for file_info in output_files:
        file_path = os.path.join(workspace, file_info["name"])
        session["results"][file_info["id"]] = {
            "name": file_info["name"],
            "path": file_path
        }
    return ExecuteResponse(
        stdout=stdout,
        stderr=stderr,
        files=output_files,
        session_id=session_id
    )
@app.get("/files/{session_id}")
async def list_files(
    session_id: str,
    detail: str = "full",
    x_api_key: Optional[str] = Header(None, alias="X-API-Key")
):
    """
    List files in a session.
    Matches @librechat/agents file listing API.
    """
    if not verify_api_key(x_api_key):
        raise HTTPException(status_code=401, detail="Invalid API key")
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    session = sessions[session_id]
    workspace = session["workspace"]
    files = []
    for item in os.listdir(workspace):
        if item.startswith('_') or item.startswith('.'):
            continue
        file_path = os.path.join(workspace, item)
        if os.path.isfile(file_path):
            file_info = {
                "name": item,
                "size": os.path.getsize(file_path),
            }
            if detail == "full":
                file_info["path"] = file_path
            files.append(file_info)
    return {"files": files, "session_id": session_id}
@app.get("/download/{session_id}/{file_id}")
async def download_file(
    session_id: str,
    file_id: str,
    kind: Optional[str] = None,
    id: Optional[str] = None,
    version: Optional[str] = None,
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
):
    """Download a generated file from a session.

    Matches LibreChat's codeapi `/download/{session_id}/{fileId}` endpoint,
    which LibreChat calls both in `getCodeOutputDownloadStream` (files.js proxy)
    and while processing code output (`processCodeOutput`). The query params
    kind/id/version are sent by LibreChat for sessionKey resolution but are
    ignored here since sessions are keyed by session_id. Returns the file
    bytes directly so the caller can stream / save them.
    """
    if not verify_api_key(x_api_key):
        raise HTTPException(status_code=401, detail="Invalid API key")
    if not validate_session_id(session_id) or not validate_session_id(file_id):
        raise HTTPException(status_code=400, detail="Invalid session or file id")
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    session = sessions[session_id]
    file_meta = session.get("results", {}).get(file_id)
    if not file_meta:
        raise HTTPException(status_code=404, detail="File not found")
    file_path = file_meta.get("path")
    if not file_path or not os.path.isfile(file_path):
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(
        file_path,
        filename=file_meta.get("name", os.path.basename(file_path)),
        media_type=None,
    )


@app.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key")
):
    """
    Upload a file to a session.
    Matches LibreChat's Code.js upload expectations:
    - Returns: { message: 'success', session_id, files: [{ fileId, filename }] }
    """
if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Code Command API')
    parser.add_argument('--host', default='0.0.0.0', help='Host to bind')
    parser.add_argument('--port', type=int, default=8095, help='Port to bind')
    args = parser.parse_args()

    logger.info(f"Starting Code Command API on {args.host}:{args.port}")
    uvicorn.run(app, host=args.host, port=args.port, log_level='info')