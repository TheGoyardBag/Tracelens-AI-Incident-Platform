# Implementation references and further reading

Primary documentation consulted for API shapes and ecosystem behavior. The project does not copy these pages or claim benchmark results from them.

- Next.js App Router installation and requirements: https://nextjs.org/docs/app/getting-started/installation
- Published direct dependency metadata: https://registry.npmjs.org/next/latest and https://registry.npmjs.org/react/latest
- LangGraph graph API: https://docs.langchain.com/oss/python/langgraph/graph-api
- Anthropic tool use: https://platform.claude.com/docs/en/agents-and-tools/tool-use/overview
- OpenTelemetry protocol: https://opentelemetry.io/docs/specs/otlp/
- PyTorch documentation: https://docs.pytorch.org/
- SQLAlchemy documentation: https://docs.sqlalchemy.org/en/20/
- scikit-learn group-aware evaluation: https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.GroupKFold.html
- MLflow tracking: https://mlflow.org/docs/latest/ml/tracking/
- External evaluation follow-up: https://github.com/phamquiluan/RCAEval

No RCAEval telemetry or baseline source is included here. Follow upstream instructions and licensing before adding it. The optional OTLP adapter supports a trace-file subset only, not the entire protocol.
