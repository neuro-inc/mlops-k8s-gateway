#!/bin/bash

SERVICE_POD=$(kubectl -n mlops-integrations get po -l run=mlops-kube-gateway -o jsonpath='{.items[*].metadata.name}')
echo SERVICE_POD=${SERVICE_POD}
kubectl -n mlops-integrations logs -f ${SERVICE_POD}

kubectl -n seldon get seldondeployment # my-model -o yaml

kubectl -n seldon get po -l seldon-app=my-model-predictor
MODEL_POD=$(kubectl -n seldon get po -l seldon-app=my-model-predictor -o jsonpath='{.items[*].metadata.name}' | awk '{print $1}')
echo MODEL_POD=$MODEL_POD
kubectl -n seldon logs $MODEL_POD -c model


INFERENCE_URL=https://seldon.onprem-poc.org.neu.ro/seldon/seldon/my-model
curl -k -X POST -F binData=@/home/ay/Downloads/cute.jpg ${INFERENCE_URL}/api/v1.0/predictions

