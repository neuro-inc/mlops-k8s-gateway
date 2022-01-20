RELEASE_NAME ?= mlflow2seldon
HELM_CHART = mlflow2seldon

DEPLOYMENT_NAMESPACE ?= mlops-integrations

M2S_MLFLOW_NEURO_TOKEN ?= $(shell neuro config show-token)
M2S_MLFLOW_HOST ?= $(shell read -p "MLFlow server hostname: " x; echo $$x)
M2S_MLFLOW_STORAGE_ROOT ?= $(shell read -p "MLFlow artifact root path on storage: " x; echo $$x)
M2S_SELDON_NEURO_DEF_IMAGE ?= $(shell read -p "Default Seldon deployment image name: " x; echo $$x)
M2S_SRC_NEURO_CLUSTER ?= $(shell read -p "Neuro cluster where MLFlow is running: " x; echo $$x)


setup:
	pip install -r requirements/syntax.txt
	pre-commit install

lint: format
	mypy mlflow2seldon setup.py

format:
	pre-commit run --all-files --show-diff-on-failure

_helm_fetch:
	rm -rf temp_deploy
	mkdir -p temp_deploy/$(RELEASE_NAME)
	cp -RfT deploy/$(HELM_CHART) temp_deploy/$(RELEASE_NAME)
	find temp_deploy/$(RELEASE_NAME) -type f -name 'values*' -delete

_helm_expand_vars:
	export M2S_MLFLOW_NEURO_TOKEN=$(M2S_MLFLOW_NEURO_TOKEN); \
	export M2S_MLFLOW_HOST=$(M2S_MLFLOW_HOST); \
	export M2S_MLFLOW_STORAGE_ROOT=$(M2S_MLFLOW_STORAGE_ROOT); \
	export M2S_SELDON_NEURO_DEF_IMAGE=$(M2S_SELDON_NEURO_DEF_IMAGE); \
	export M2S_SRC_NEURO_CLUSTER=$(M2S_SRC_NEURO_CLUSTER); \
	neuro config switch-cluster $${M2S_SRC_NEURO_CLUSTER}; \
	cat deploy/$(HELM_CHART)/values-make.yaml | envsubst > temp_deploy/$(RELEASE_NAME)/values-make.yaml
	cp deploy/$(HELM_CHART)/values.yaml temp_deploy/$(RELEASE_NAME)/values.yaml
	helm lint temp_deploy/$(RELEASE_NAME) -f temp_deploy/$(RELEASE_NAME)/values.yaml -f temp_deploy/$(RELEASE_NAME)/values-make.yaml

helm_deploy: _helm_fetch _helm_expand_vars
	helm upgrade $(RELEASE_NAME) \
		temp_deploy/$(RELEASE_NAME) -f temp_deploy/$(RELEASE_NAME)/values.yaml -f temp_deploy/$(RELEASE_NAME)/values-make.yaml \
		--create-namespace --namespace $(DEPLOYMENT_NAMESPACE) --install --wait --timeout 600s

helm_delete:
	helm uninstall --namespace $(DEPLOYMENT_NAMESPACE) $(RELEASE_NAME)
