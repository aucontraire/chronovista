#!/bin/bash
# Run only unit tests
echo "Running unit tests..."
pytest tests/unit/ -v --cov=chronovista --cov-report=term-missing "$@"