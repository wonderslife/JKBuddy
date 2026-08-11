# Shared Assets

This folder is mounted read-only at `/mnt/shared` inside the sandbox container.

Use it to provide reusable resources to AI-generated code:

```
shared_assets/
├── icons/       # SVG icons for presentations/charts
├── templates/   # PPTX/XLSX templates
├── fonts/       # Custom fonts (TTF/OTF)
└── utils/       # Python helper modules
```

## Example Usage in AI Code

```python
# Access a template
from pathlib import Path
template = Path("/mnt/shared/templates/report.pptx")

# Use a helper module
import sys
sys.path.insert(0, "/mnt/shared/utils")
from chart_helpers import create_chart
```

This folder is optional - the sandbox works fine without it.
