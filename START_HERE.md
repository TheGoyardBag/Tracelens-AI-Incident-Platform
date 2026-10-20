# Start TraceLens

This folder is the repository. Upload its **contents** to GitHub, not just the ZIP.

## 1. Run the working local app

From this folder, using Python 3.11–3.13:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev,otel]"
python scripts/setup.py
python -m tracelens.cli serve
```

On Windows PowerShell, activate with `.\.venv\Scripts\Activate.ps1` instead.

Open **http://127.0.0.1:8000**, enter the generated token, and click **New investigation**. The trained model and synthetic demo incidents are already included. No paid model API is required for this mode.

## 2. Try the React/Next.js frontend

With the API still running, open another terminal:

```bash
cd web
npm install
npm run typecheck
npm run build
npm run start
```

Open **http://localhost:3000** and use the same token. The source is provided, but the full npm build could not be run in the creation environment. Review and commit the generated package-lock.json.

## 3. Test, understand, and publish

- [README](README.md): architecture, model training, data, optional integrations and setup.
- [Validation record](reports/VALIDATION.md): what passed and what still needs validation.
- [Model card](docs/MODEL_CARD.md): limitations and actual synthetic evaluation.
- [GitHub publishing guide](docs/PUBLISH.md): commands and repository description.
- [Portfolio guide](docs/PORTFOLIO.md): résumé wording, interview questions and worthwhile extensions.

Do not commit `.env`, databases, imported telemetry, dependencies or caches. Keep the generated/synthetic-data labeling and distinguish the offline evidence workflow from the optional hosted LLM mode.
