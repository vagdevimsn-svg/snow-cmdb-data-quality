.PHONY: install test lint report mock docker
install:   ## install with dev tools
	pip install -e ".[dev]"
test:      ## run tests with coverage
	pytest -q --cov=cmdb_dq --cov-report=term-missing
lint:
	ruff check .
report:    ## regenerate the sample reports in docs/
	python -m cmdb_dq --input sample_data/cmdb_export.json --format md --output docs/sample_report.md
	python -m cmdb_dq --input sample_data/cmdb_export.json --format html --output docs/sample_report.html
	python -m cmdb_dq --input sample_data/cmdb_export.json --format csv --output docs/remediation_worklist.csv
mock:      ## run the mock Table API on :8080
	python -m cmdb_dq.mock_server --port 8080
docker:
	docker build -t cmdb-dq . && docker run --rm cmdb-dq
