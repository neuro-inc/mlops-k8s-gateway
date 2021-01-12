# platform-integrations

Web service for integration of third-party tools that require direct access to k8s (like Seldon, Algorithmia, MLFlow) with Neu.ro platform.

Maintained by Neu.ro MLOps team.



# ==
# see https://github.com/adriangonz/mlflow-talk/blob/master/README.ipynb

helm install seldon-core seldon-core-operator \
    --repo https://storage.googleapis.com/seldon-charts \
    --set usageMetrics.enabled=true \
    --namespace seldon-system


# How to auth neuro in a pod:
$ TOKEN=$(neuro config show-token) 
$ CLUSTER=$(neuro config show | grep "Current Cluster" | awk "{print \$NF}")
$ API_URL=$(neuro config show | grep "API URL" | awk "{print \$NF}") 
$ NEURO_PASSED_CONFIG=$(echo '{"token": "'$TOKEN'", "cluster": "'$CLUSTER'", "url": "'$API_URL'"}' | base64)
# neuro run -e NEURO_PASSED_CONFIG=$NEURO_PASSED_CONFIG neuromation/base bash

# How to auth kubectl in a pod: