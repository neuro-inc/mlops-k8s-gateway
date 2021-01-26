#!/bin/bash

kubectl -n seldon get seldondeployment # my-model -o yaml

kubectl -n seldon get po -l seldon-app=my-model-predictor
MODEL_POD=$(kubectl -n seldon get po -l seldon-app=my-model-predictor -o jsonpath='{.items[*].metadata.name}' | awk '{print $1}')
echo MODEL_POD=$MODEL_POD
kubectl -n seldon get po $MODEL_POD
# kubectl -n seldon logs $MODEL_POD -c model

INFERENCE_URL=https://seldon.onprem-poc.org.neu.ro/seldon/seldon/my-model
curl -k -X POST -F binData=@n02085936_1244_maltese_dog.jpg ${INFERENCE_URL}/api/v1.0/predictions
curl -k -X POST -F binData=@n02088094_12364_afghan_hound.jpg ${INFERENCE_URL}/api/v1.0/predictions

