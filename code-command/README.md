```
  ██████╗ ██████╗ ██████╗ ███████╗     ██████╗ ██████╗ ███╗   ███╗███╗   ███╗ █████╗ ███╗   ██╗██████╗
 ██╔════╝██╔═══██╗██╔══██╗██╔════╝    ██╔════╝██╔═══██╗████╗ ████║████╗ ████║██╔══██╗████╗  ██║██╔══██╗
 ██║     ██║   ██║██║  ██║█████╗      ██║     ██║   ██║██╔████╔██║██╔████╔██║███████║██╔██╗ ██║██║  ██║
 ██║     ██║   ██║██║  ██║██╔══╝      ██║     ██║   ██║██║╚██╔╝██║██║╚██╔╝██║██╔══██║██║╚██╗██║██║  ██║
 ╚██████╗╚██████╔╝██████╔╝███████╗    ╚██████╗╚██████╔╝██║ ╚═╝ ██║██║ ╚═╝ ██║██║  ██║██║ ╚████║██████╔╝
  ╚═════╝ ╚═════╝ ╚═════╝ ╚══════╝     ╚═════╝ ╚═════╝ ╚═╝     ╚═╝╚═╝     ╚═╝╚═╝  ╚═╝╚═╝  ╚═══╝╚═════╝
```

# Code Command

A **self-hosted, sandboxed code interpreter** for AI agents. Drop-in replacement for LibreChat's hosted code interpreter (`code.librechat.ai`).

Run Python code locally in secure Docker containers instead of sending it to external services.

**Works seamlessly with LibreChat** - Agents, Assistants, and regular chats. Just point LibreChat to your Code Command instance and everything works: code execution, file uploads, file downloads, charts, documents - no modifications needed.

## Why Self-Host?

- **Privacy**: Code never leaves your infrastructure
- **Customization**: Add any Python packages you need
- **No rate limits**: Execute as much as you want
- **Cost**: No per-execution fees
- **Control**: Full visibility into what's running

## Features

- **Drop-in Replacement**: Works with LibreChat out of the box - file uploads, downloads, and code execution just work
- **Docker Sandboxing**: Secure isolation with no network access, memory limits, and timeouts
- **Multi-user Isolation**: Each user's files are completely isolated
- **Pre-loaded Packages**: numpy, pandas, matplotlib, seaborn, scikit-learn, python-pptx, and more
- **Shared Assets**: Optional folder for your own icons, templates, and helper utilities

## Quick Start

### Option 1: Docker Compose (Recommended)

```bash
# Clone the repository
git clone https://github.com/ryanfortin/code-command.git
cd code-command

# Build the sandbox image first
docker build -t code-sandbox:latest .

# Copy and configure environment
cp .env.example .env
# Edit .env with your API key

# Start the service
docker-compose up -d
```

### Option 2: Manual Setup

```bash
# 1. Build the Docker sandbox image
docker build -t code-sandbox:latest .

# 2. Install Python dependencies
pip install -r requirements.txt

# 3. Run the API server
python code_interpreter.py --port 8095
```

## LibreChat Integration

Code Command is a **drop-in replacement** for LibreChat's hosted code interpreter. Uploading files, executing code, generating charts and documents - everything works the same, just running on your own infrastructure.

### Step 1: Set Your API Key in Code Command

Edit your Code Command `.env` file:
```env
CODE_API_KEY=your-secret-key-here
```

### Step 2: Configure LibreChat

Add to your LibreChat `.env` file:
```env
# Point to your Code Command instance
# Use host.docker.internal if LibreChat runs in Docker (most common)
# Use localhost if LibreChat runs directly on host
LIBRECHAT_CODE_BASEURL=http://host.docker.internal:8095

# Must match the CODE_API_KEY you set above
LIBRECHAT_CODE_API_KEY=your-secret-key-here
```

### Step 3: (Optional) Configure librechat.yaml

Only needed if using custom config:
```yaml
endpoints:
  agents:
    codeInterpreter:
      url: "http://host.docker.internal:8095"
      apiKey: "${LIBRECHAT_CODE_API_KEY}"
```

### Step 4: Restart Both Services

```bash
# Restart Code Command
docker-compose restart

# Restart LibreChat
cd /path/to/librechat && docker-compose restart
```

That's it! LibreChat will now use your self-hosted Code Command instance.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         AI Agent / LibreChat                        │
│         (Uses @librechat/agents which calls code interpreter)       │
└───────────────────────────────────┬─────────────────────────────────┘
                                    │ HTTP API
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    code_interpreter.py (FastAPI)                    │
│                       Running on port 8095                          │
│                                                                     │
│  - Receives code execution requests                                 │
│  - Manages sessions & user isolation                                │
│  - Spawns Docker containers for each execution                      │
│  - Returns stdout, stderr, and output files                         │
└───────────────────────────────────┬─────────────────────────────────┘
                                    │ Docker API
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│              Docker Container (code-sandbox:latest)                 │
│                                                                     │
│  SECURITY CONSTRAINTS:                                              │
│  - network_mode="none"     (no internet access)                     │
│  - mem_limit="256m"        (memory cap)                             │
│  - pids_limit=50           (prevent fork bombs)                     │
│  - read_only=True          (immutable root filesystem)              │
│  - no-new-privileges       (no privilege escalation)                │
│  - 120 second timeout      (execution time limit)                   │
│                                                                     │
│  /workspace (read-write mount) ←→ Host session directory            │
│  /mnt/shared (read-only mount) ←→ Shared assets (icons, helpers)    │
└─────────────────────────────────────────────────────────────────────┘
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/exec` | POST | Execute code, return stdout/stderr/files |
| `/upload` | POST | Upload file to session |
| `/files/{session_id}` | GET | List files in session |
| `/download/{session_id}/{file_id}` | GET | Download file |
| `/sessions/{session_id}` | DELETE | Clean up session |
| `/health` | GET | Health check |

### Execute Code

```bash
curl -X POST http://localhost:8095/exec \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-key" \
  -d '{
    "code": "import pandas as pd\nprint(pd.DataFrame({\"a\": [1,2,3]}))",
    "lang": "python"
  }'
```

Response:
```json
{
  "stdout": "   a\n0  1\n1  2\n2  3\n",
  "stderr": "",
  "files": [],
  "session_id": "uuid-here"
}
```

## Shared Assets (Optional)

The `shared_assets/` folder is mounted read-only at `/mnt/shared` inside the sandbox. Use it to provide reusable resources to AI-generated code:

```
shared_assets/
├── icons/       # SVG icons for presentations
├── templates/   # PPTX/XLSX templates
├── fonts/       # Custom fonts (TTF/OTF)
└── utils/       # Python helper modules
```

Example usage in AI-generated code:
```python
import sys
sys.path.append('/mnt/shared/utils')
from my_helpers import create_chart
```

This folder is optional - the sandbox works fine without any shared assets.

## Security Model

### Container Isolation

Every code execution runs in a **fresh Docker container**:

```python
container = client.containers.run(
    image="code-sandbox:latest",
    network_mode="none",          # No network access
    mem_limit="256m",             # Max 256MB RAM
    memswap_limit="256m",         # No swap
    pids_limit=50,                # Prevent fork bombs
    read_only=True,               # Read-only root filesystem
    security_opt=["no-new-privileges"],
)
```

### What This Prevents

| Attack | Protection |
|--------|------------|
| Data exfiltration | `network_mode="none"` |
| Crypto mining | No network + CPU limits |
| Fork bombs | `pids_limit=50` |
| Disk filling | Read-only root + 100MB workspace limit |
| Container escape | `no-new-privileges`, non-root user |
| Infinite loops | 120 second timeout |
| Memory exhaustion | 256MB hard limit |
| CPU exhaustion | 0.5 CPU core limit |

### Session Isolation

Each session gets its own isolated workspace:

```
/tmp/code_command/
├── {session-id-1}/         # Session workspace
└── {session-id-2}/         # Cleaned up after 24h
```

Files exist only during the session and are automatically cleaned up after 24 hours.

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `CODE_API_KEY` | `code-command-dev-key` | API authentication key |
| `CODE_WORK_DIR` | `/tmp/code_command` | Base directory for sessions |
| `SHARED_ASSETS_PATH` | `./shared_assets` | Path to shared assets |
| `CODE_EXEC_TIMEOUT` | `120` | Execution timeout (seconds) |
| `CPU_LIMIT` | `0.5` | CPU cores per execution (0.5 = half core) |
| `WORKSPACE_SIZE_LIMIT` | `104857600` (100MB) | Max workspace size per session |
| `SESSION_MAX_AGE_HOURS` | `24` | Auto-cleanup threshold |
| `CLEANUP_INTERVAL_MINUTES` | `60` | Cleanup frequency |
| `MAX_UPLOAD_SIZE` | `52428800` (50MB) | Max upload size |
| `CORS_ORIGINS` | `localhost:3080,3000` | Allowed CORS origins |
| `SANDBOX_IMAGE` | `code-sandbox:latest` | Docker image for sandbox |

## Pre-installed Packages

The sandbox includes these Python packages:

**Data Science**: numpy, pandas, scipy, scikit-learn, sympy

**Visualization**: matplotlib, seaborn, graphviz

**Documents**: python-pptx, openpyxl, xlrd, pillow

**Web/Parsing**: requests, beautifulsoup4, lxml

**Fonts**: Liberation Sans/Serif/Mono, DejaVu (for professional charts)

## Example Capabilities

### Create Charts
```python
import matplotlib.pyplot as plt
plt.bar(['Jan', 'Feb', 'Mar'], [100, 150, 200])
plt.savefig('chart.png', dpi=150)
```

### Generate PowerPoints
```python
from pptx import Presentation
prs = Presentation()
slide = prs.slides.add_slide(prs.slide_layouts[1])
slide.shapes.title.text = "Q4 Results"
prs.save('report.pptx')
```

### Create Mind Maps
```python
from graphviz import Digraph
g = Digraph('MindMap', format='png')
g.attr('node', shape='box', fontname='Liberation Sans')
g.node('center', 'Main Topic')
g.node('a', 'Subtopic')
g.edge('center', 'a')
g.render('/workspace/mindmap', cleanup=True)
```

## FAQ

### How do I add more Python packages?

Edit the `Dockerfile` and add packages to the `pip install` line:

```dockerfile
RUN pip install --no-cache-dir \
    numpy \
    pandas \
    # ... existing packages ...
    your-new-package
```

Then rebuild: `docker build -t code-sandbox:latest .`

### How do I add custom fonts?

Add font files to the Dockerfile:

```dockerfile
COPY fonts/*.ttf /usr/share/fonts/truetype/custom/
RUN fc-cache -f
```

### How do I increase resource limits?

Edit your `.env` file:

```env
CPU_LIMIT=1.0                    # Full CPU core
WORKSPACE_SIZE_LIMIT=209715200   # 200MB
CODE_EXEC_TIMEOUT=300            # 5 minutes
```

Or modify `docker-compose.yml` for the sandbox container's memory limits.

### Can I add custom templates or icons?

Yes! Add files to the `shared_assets/` folder:

- `shared_assets/templates/` - PowerPoint templates (.pptx)
- `shared_assets/icons/` - Icons organized by category
- `shared_assets/utils/` - Python helper modules

These are mounted read-only at `/mnt/shared` inside the sandbox.

### Can I use this with other AI platforms?

Code Command implements a REST API compatible with LibreChat's code interpreter protocol. Other platforms could integrate if they support the same API format:

- `POST /exec` - Execute code
- `POST /upload` - Upload files
- `GET /download/{session_id}/{file_id}` - Download files

## Credits

Built for **[LibreChat](https://github.com/danny-avila/LibreChat)** - the powerful open-source AI chat platform.

## License

MIT - See [LICENSE](LICENSE) for details.
