#!/bin/bash

# Run the gateway service
kubectl config use-context onprem-poc

kubectl create namespace mlops-integrations
neuro config switch-cluster neuro-compute
kubectl -n mlops-integrations delete secret neuro-token
kubectl -n mlops-integrations create secret generic neuro-token --from-literal=neuro-compute-token=$(neuro config show-token)


kubectl -n seldon get seldondeployment # my-model -o yaml

kubectl -n seldon delete seldondeployment my-model
kubectl delete -f k8s/seldon-roles.yaml
kubectl delete -f k8s/deployment.yaml


kubectl apply -f k8s/seldon-roles.yaml
kubectl apply -f k8s/deployment.yaml


kubectl -n mlops-integrations get po -l run=mlops-kube-gateway
SERVICE_POD=$(kubectl -n mlops-integrations get po -l run=mlops-kube-gateway -o jsonpath='{.items[*].metadata.name}')
echo SERVICE_POD=${SERVICE_POD}


kubectl -n mlops-integrations logs -f ${SERVICE_POD}
