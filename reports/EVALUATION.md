# Synthetic-data evaluation

**These are measured results on generated data, not production incidents or RCAEval.**

Models and temperature scaling are fitted using training/validation only. Test and challenge sets are untouched during selection.

| Model | Test top-1 | Test top-3 | Challenge top-1 | Test MRR |
|---|---:|---:|---:|---:|
| full | 98.1% | 100.0% | 98.6% | 0.990 |
| no_logs | 95.2% | 100.0% | 94.4% | 0.976 |
| no_graph | 99.0% | 100.0% | 99.3% | 0.995 |
| gradient_boosting | 93.3% | 100.0% | 95.1% | 0.963 |
| error_latency_heuristic | 38.5% | 87.5% | 31.2% | 0.618 |

Split sizes: `{'train': 374, 'validation': 98, 'test': 104, 'challenge': 144}`.
Training time in this environment: 19.841 seconds.

The neural model is not required to beat gradient boosting. Report the result, not a preferred narrative.
The no-log and no-graph models are separately retrained ablations, not an attribution method.
The challenge set holds out service/fault combinations; it does not establish performance on unseen fault mechanisms.
Both observations of each fault experiment remain in the same split. Bootstrap intervals are over groups, not observations.
Check `evaluation.json` for selective accuracy, coverage, NLL, ECE, and confidence intervals.
