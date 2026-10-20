# Make this your own portfolio project

## A defensible résumé entry after running and understanding it

**AI Incident Investigation Platform** — Built and evaluated a full-stack incident investigation application using PyTorch, FastAPI, and Next.js, combining a trained service-ranking model, evidence-linked tool workflows, grouped synthetic-data evaluation, and persistent investigation history.

Do not claim production accuracy, paying users, live AWS deployment, autonomous remediation, independently completed historical work, or a foundation-model fine-tune. Do not claim use of the optional hosted model, LangGraph, MLflow, PostgreSQL or Next.js production deployment until you actually validate those paths yourself.

A more specific measured line you can substantiate from the supplied reports is: “Compared neural, gradient-boosting and heuristic rankers on 720 generated incident observations with experiment-group splits and independently retrained feature ablations.” Do not omit “generated” or “synthetic.”

## Explain the design in an interview

An incident contains aligned service metrics, logs and request spans. A shared neural model scores each candidate service using temporal, text and statistical features. A read-only investigation then retrieves supporting evidence, verifies source IDs, and presents a hypothesis with its limitations. Human feedback and review records are persisted, but the tool never changes infrastructure.

The neural network is genuinely trained here. The default investigation policy is deterministic and is not passed off as an LLM. Hosted mode is optional and has a different tool-selection loop. Labels are in a separate file and never enter that loop.

## Questions worth preparing for

Why are random row-level splits unsafe? Why can the no-graph ablation outperform the full model? What does top-3 accuracy mean with only six candidates? Why is a softmax score not a probability of causation? What does temperature scaling fix and what does it not fix? How would you add missingness masks? How would you replace an in-process worker with a durable queue? How do you prevent a retrieved log from becoming an instruction? What does citation validation fail to establish?

## Three changes that would materially deepen the project

1. Evaluate a real benchmark with documented preprocessing, grouped splits and an independently implemented baseline. Keep those results separate from synthetic results.
2. Add missing-data indicators and a stronger text encoder; run multiple seeds and show whether either change improves the held-out result.
3. Validate the Next.js production build, hosted provider integration and PostgreSQL deployment, then add a short recorded demo and a concrete failure analysis.

Use a real Git history for the changes you make next. Keep the AI-assistance acknowledgement and your own design notes. Demonstrating that you can inspect, test and improve the implementation is more useful than presenting generated code as something you have already mastered.
