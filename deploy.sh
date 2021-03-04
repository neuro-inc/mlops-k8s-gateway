#!/bin/bash

# Cleaup all
kubectl config use-context onprem-poc   # TODO: parameterize
kubectl -n mlops-integrations delete secret neuro-config      # TODO: parameterize
kubectl delete -f k8s/seldon-roles.yaml
kubectl delete -f k8s/deployment.yaml

# Deploy
kubectl config use-context onprem-poc
kubectl create namespace mlops-integrations || echo Namespace exists
neuro config switch-cluster neuro-compute   # TODO: parameterize

MLFLOW_HOST=https://ml-recipe-bone-age-mlflow-server--yevheniisemendiak.jobs.neuro-compute.org.neu.ro
MLFLOW_STORAGE_ROOT=storage:ml_recipe_bone_age/mlruns   # TODO: parameterize all those values
SELDON_IMAGE_BASE_NAME=image:ml_recipe_bone_age/inference
kubectl -n mlops-integrations create secret generic neuro-config \
    --from-literal=neuro_token=$(neuro config show-token) \
    --from-literal=mlflow_host=$MLFLOW_HOST\
    --from-literal=mlflow_storage_root=$MLFLOW_STORAGE_ROOT\
    --from-literal=seldon_neuro_img_base_name=$SELDON_IMAGE_BASE_NAME\ 
kubectl apply -f k8s/seldon-roles.yaml
kubectl apply -f k8s/deployment.yaml


# Verify
# get seldon deployments
# kubectl -n seldon get seldondeployment # my-model -o yaml
# 
kubectl -n mlops-integrations get po -l run=mlops-kube-gateway

SERVICE_POD=$(kubectl -n mlops-integrations get po -l run=mlops-kube-gateway -o jsonpath='{.items[*].metadata.name}')
echo SERVICE_POD=${SERVICE_POD}

kubectl -n mlops-integrations logs -f ${SERVICE_POD}
kubectl port-forward svc/seldon-core-analytics-grafana 3000:80 -n seldon-system
