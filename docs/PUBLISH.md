# Publish to your GitHub

Extract the ZIP. Open a terminal in the `tracelens` folder that contains README.md and pyproject.toml. Do not upload the ZIP as the repository's only file.

Run the project and review its results before publishing. Keep `.env`, `.venv`, `.tracelens`, imported telemetry, node_modules and build caches out of Git. The included `.gitignore` covers these paths. The trained model, generated data and validation reports are intentionally small enough to track.

## With the GitHub CLI

After installing Git and GitHub CLI and signing in:

```bash
git init -b main
git add .
git status
# Inspect the staged files before committing.
git commit -m "Add TraceLens incident investigation prototype"
gh repo create tracelens-ai-incident-platform --private --source=. --remote=origin --push
```

Use a different repository name if that name already exists in your account. Start private while checking everything; change visibility after reviewing secrets, licenses, claims and documentation.

## Without the GitHub CLI

Create an empty repository on GitHub. Then follow GitHub's displayed “push an existing repository” instructions from this folder. Alternatively, upload the extracted source folders and files through the website; preserve the directory structure and hidden `.github` files. Command-line Git is less error-prone for a multi-directory project.

## Suggested repository description

Evidence-backed incident investigation with PyTorch service ranking, a FastAPI backend, a Next.js workspace, reproducible synthetic evaluations, and bounded read-only AI workflows.

Suggested topics: machine-learning, pytorch, ai-engineering, fastapi, nextjs, root-cause-analysis, observability, opentelemetry, llm, evaluation.

Run `npm install`, `npm run typecheck` and `npm run build` in `web/`. Commit the generated package-lock.json. Check the first GitHub Actions run before adding a passing-build badge. The supplied workflow has not run in your GitHub account yet.
