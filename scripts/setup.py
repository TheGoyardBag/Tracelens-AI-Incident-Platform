#!/usr/bin/env python3
"""Generate local credentials. Never overwrites an existing .env."""
from pathlib import Path
import os
import secrets
root=Path(__file__).resolve().parents[1]
path=root/".env"
if path.exists():
    print("Existing .env left unchanged. Your local token is TRACELENS_API_TOKEN in that file.")
else:
    token=secrets.token_urlsafe(32)
    path.write_text(f"TRACELENS_API_TOKEN={token}\nTRACELENS_ALLOW_EXTERNAL_TELEMETRY=false\n# Optional hosted model (enable export consent only for data you may share):\n# ANTHROPIC_API_KEY=\n# TRACELENS_LLM_MODEL=\n")
    os.chmod(path,0o600)
    print("Created .env (not tracked by Git). Paste this token into the local dashboard:")
    print(token)
print("Run: python -m tracelens.cli serve")
