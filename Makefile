.PHONY: setup serve test train demo web
setup:
	python -m pip install -e ".[dev,otel]"
	python scripts/setup.py
serve:
	python -m tracelens.cli serve
test:
	python -m pytest -q
	node --test tests/frontend.test.mjs
train:
	python scripts/generate_data.py
	python -m tracelens.ml.train
	python scripts/prepare_demo.py
demo:
	python examples/otel_lab.py --out examples/lab-traces.json
	python scripts/import_otlp.py examples/lab-traces.json --id local-otel-lab --out examples/my-lab-incident.json
web:
	cd web && npm install && npm run dev
