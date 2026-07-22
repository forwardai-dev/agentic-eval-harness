.PHONY: install test run determinism eval

install:
	pip install -r requirements.txt --break-system-packages || pip install -r requirements.txt

test:
	AEH_OUT_DIR=none python3 -m pytest -q

determinism:
	AEH_OUT_DIR=none python3 scripts/determinism_check.py

run:
	uvicorn aeh.api:app --reload --port 8000

eval:
	AEH_OUT_DIR=none python3 -c "from aeh.eval import run_eval_suite; import json; print(json.dumps(run_eval_suite(), indent=2))"
