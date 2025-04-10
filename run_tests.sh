#!/bin/bash

# Run unit tests
pipenv run coverage run --source=src -m unittest discover -s tests/unit
mv .coverage .coverage.unit  # Move the coverage data to .coverage.unit

# Run component tests
pipenv run coverage run --source=src -m unittest discover -s tests/component
mv .coverage .coverage.component  # Move the coverage data to .coverage.component

pipenv run coverage combine .coverage.unit .coverage.component
pipenv run coverage report --omit="tests/*"