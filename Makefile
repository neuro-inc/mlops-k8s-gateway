IMAGE = platformintegrations:latest
IMAGE_ALIAS ?= image:/onprem-poc/artemyushkovskiy/$(IMAGE)
# IMAGE_REF ?= registry.onprem-poc.org.neu.ro/artemyushkovskiy/$(IMAGE)

setup:
	pip install -U pip
	pip install -e .
	pip install -r requirements/syntax.txt

lint: format
	mypy platform_integrations tests setup.py

format:
	pre-commit run --all-files --show-diff-on-failure

neuro_build:
	pip install -U neuro-extras
	neuro-extras image build -f Dockerfile . $(IMAGE_ALIAS)
