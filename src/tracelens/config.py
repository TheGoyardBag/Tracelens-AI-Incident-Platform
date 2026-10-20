from __future__ import annotations
import os
import secrets
from dataclasses import dataclass
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]


def load_dotenv(path: Path):
    if not path.exists():return
    for line in path.read_text().splitlines():
        line=line.strip()
        if not line or line.startswith("#") or "=" not in line:continue
        key,value=line.split("=",1)
        if key.startswith(("TRACELENS_","ANTHROPIC_")) or key=="DATABASE_URL":
            os.environ.setdefault(key,value.strip().strip('"').strip("'"))


@dataclass
class Settings:
    root: Path
    token: str
    database_url: str
    model_dir: Path
    demo_file: Path
    provider_key: str=""
    provider_model: str=""
    allow_external_telemetry: bool=False
    allowed_hosts: tuple[str,...]=("localhost","127.0.0.1","testserver","api")
    cors_origins: tuple[str,...]=("http://localhost:3000","http://127.0.0.1:3000")

    @property
    def llm_ready(self):return bool(self.provider_key and self.provider_model and self.allow_external_telemetry)

    @classmethod
    def from_env(cls):
        root=Path(os.environ.get("TRACELENS_ROOT",ROOT)).resolve()
        load_dotenv(root/".env")
        token=os.environ.get("TRACELENS_API_TOKEN","")
        if len(token)<24:raise ValueError("Run `python scripts/setup.py` to generate a local API token, or set TRACELENS_API_TOKEN (24+ characters)")
        state=root/".tracelens";state.mkdir(exist_ok=True)
        return cls(root,token,os.environ.get("DATABASE_URL",f"sqlite:///{state/'app.db'}"),
            Path(os.environ.get("TRACELENS_MODEL_DIR",root/"artifacts")),root/"data/demo-incidents.jsonl",
            os.environ.get("ANTHROPIC_API_KEY",""),os.environ.get("TRACELENS_LLM_MODEL",""),
            os.environ.get("TRACELENS_ALLOW_EXTERNAL_TELEMETRY","").lower()=="true",
            tuple(os.environ.get("TRACELENS_ALLOWED_HOSTS","localhost,127.0.0.1,testserver,api").split(",")),
            tuple(os.environ.get("TRACELENS_CORS_ORIGINS","http://localhost:3000,http://127.0.0.1:3000").split(",")))
