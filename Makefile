.PHONY: all data test airflow hadoop train serve ollama
all: ; ./run-all.sh
data: ; .venv/bin/python -m receipts.generate data/receipts.csv
test: ; .venv/bin/pytest -q tests
airflow: ; ./airflow/run-airflow-tests.sh
hadoop: data ; ./hadoop/run-streaming.sh data/receipts.csv
train: ; .venv/bin/python -m ml.fraud
serve: train ; .venv/bin/uvicorn ml.api:app --port 8000
ollama: ; RUN_OLLAMA=1 .venv/bin/pytest -q -s tests/test_rag.py -k ollama
