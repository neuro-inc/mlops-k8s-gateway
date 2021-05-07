HELM_CHART = mlflow2seldon

SVC_DEPLOYMENT_NAMESPACE = mlops-integrations

M2S_MLFLOW_NEURO_TOKEN ?= $(shell neuro config show-token)
M2S_MLFLOW_HOST ?= $(shell read -p "MLFlow server hostname: " x; echo $$x)
M2S_MLFLOW_STORAGE_ROOT ?= $(shell read -p "MLFlow artifact root path on storage: " x; echo $$x)
M2S_SELDON_NEURO_DEF_IMAGE ?= $(shell read -p "Default Seldon deployment image name: " x; echo $$x)
M2S_SRC_NEURO_CLUSTER ?= $(shell read -p "Neuro cluster where MLFlow is running: " x; echo $$x)


setup:
	pip install -r requirements/syntax.txt

lint: format
	mypy platform_integrations setup.py

format:
	pre-commit run --all-files --show-diff-on-failure

_helm_fetch:
	rm -rf temp_deploy
	mkdir -p temp_deploy/$(HELM_CHART)
	cp -Rf deploy/$(HELM_CHART) temp_deploy/
	find temp_deploy/$(HELM_CHART) -type f -name 'values*' -delete

_helm_expand_vars:
	export M2S_MLFLOW_NEURO_TOKEN=$(M2S_MLFLOW_NEURO_TOKEN); \
	export M2S_MLFLOW_HOST=$(M2S_MLFLOW_HOST); \
	export M2S_MLFLOW_STORAGE_ROOT=$(M2S_MLFLOW_STORAGE_ROOT); \
	export M2S_SELDON_NEURO_DEF_IMAGE=$(M2S_SELDON_NEURO_DEF_IMAGE); \
	export M2S_SRC_NEURO_CLUSTER=$(M2S_SRC_NEURO_CLUSTER); \
	cat deploy/$(HELM_CHART)/values.yaml | envsubst > temp_deploy/$(HELM_CHART)/values.yaml

helm_deploy: _helm_fetch _helm_expand_vars
	helm upgrade $(HELM_CHART) temp_deploy/$(HELM_CHART) \
		--namespace $(SVC_DEPLOYMENT_NAMESPACE) --install --wait --timeout 600s

test-deploy:
	neuro-extras --version || pip install -U neuro-extras
	helm install deploy
	$(neuro config show-token) \
    --from-literal=mlflow_host=$MLFLOW_HOST\
    --from-literal=mlflow_storage_root=$MLFLOW_STORAGE_ROOT\
    --from-literal=seldon_neuro_img_base_name=$SELDON_IMAGE_BASE_NAME\
