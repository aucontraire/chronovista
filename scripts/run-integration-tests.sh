#!/bin/bash
# Run only integration tests
echo "Running integration tests..."
pytest tests/integration/ -v --cov=chronovista --cov-report=term-missing "$@"