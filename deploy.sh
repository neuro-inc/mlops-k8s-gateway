#!/bin/bash

# Cleaup all
kubectl config use-context onprem-poc
kubectl -n mlops-integrations delete secret neuro-config
kubectl -n seldon delete seldondeployment my-model
kubectl delete -f k8s/seldon-roles.yaml
kubectl delete -f k8s/deployment.yaml

# Deploy
kubectl config use-context onprem-poc
kubectl create namespace mlops-integrations || echo Namespace exists
MLFLOW_NEURO_USER=artemyushkovskiy
SELDON_NEURO_USER=artemyushkovskiy
neuro config switch-cluster neuro-compute
kubectl -n mlops-integrations create secret generic neuro-config \
    --from-literal=mlflow_neuro_cp_token=$(neuro config show-token) \
    --from-literal=mlflow_neuro_user=${MLFLOW_NEURO_USER} \
    --from-literal=mlflow_neuro_job_name=ml-recipe-bone-age-mlflow-server \
    --from-literal=mlflow_neuro_project_storage=storage://neuro-compute/${MLFLOW_NEURO_USER}/ml_recipe_bone_age \
    --from-literal=seldon_neuro_image=image://onprem-poc/${SELDON_NEURO_USER}/ml_recipe_bone_age/seldon:21.1.23 \
    --from-literal=seldon_model_file_name=model.pth \
    --from-literal=seldon_model_name=my-model \
    --from-literal=seldon_model_stage=Production
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
