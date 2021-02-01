#!/bin/bash

# Cleaup all
kubectl config use-context onprem-poc
kubectl -n mlops-integrations delete secret neuro-token
kubectl -n seldon delete seldondeployment my-model
kubectl delete -f k8s/seldon-roles.yaml
kubectl delete -f k8s/deployment.yaml

# Deploy
kubectl config use-context onprem-poc
kubectl create namespace mlops-integrations || echo exists!
neuro config switch-cluster neuro-compute
kubectl -n mlops-integrations create secret generic neuro-token --from-literal=neuro-compute-token=$(neuro config show-token)
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
