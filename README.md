# Neu.ro MLFlow2Seldon deployer

An integration service to deploy [MLFlow registered model](https://www.mlflow.org/docs/latest/model-registry.html) as REST/GRPC API to Kubernetes cluster using Seldon-core.

# Usage
This service is running inside of the Kubernetes cluster, where the Seldon-core is deployed.
By constantly fetching the MLFlow server registered models (running as a platform job) via MLFlow Python SDK, it synchronizes the MLFlow state to Seldon-core within the Kubernetes cluster.

For instance, if the MLFlow registered model version gets assigned to the Staging/Production stage, the corresponding model binary gets deployed from the MLFlow into the K8s cluster as the SeldonDeployment (exposing REST/GRPC APIs).
If the stage assignment gets removed/updated - the corresponding SeldonDeployment is changed respectively.

Given that, all the interaction with the service is done implicitly via the MLFlow server state. There is no need to execute particular commands/workloads against this service directly.

## Prerequisites and usage assumptions
- MLFlow 
    - is up and running as a [platform job](https://github.com/neuro-actions/mlflow)
    - disabled platform SSO;
    - artifact store as a platform storage, mounted as local path;
    - mlflow server version is at least `1.11.0`;
- Seldon 
    - SeldonDeployment container image ([model wrapper](https://docs.seldon.io/projects/seldon-core/en/stable/python/python_wrapping_docker.html)) should be stored in the platform registry, on the same cluster where MLFlow is runnnig;
    - `kubectl` tool at the time of this service deployment should be authenticated to communicate with a Kubernetes cluster, where Seldon is deployed;
    - seldon-core-operator version is at least `1.5.0`;

## Deployment
- `make helm_deploy` - will ask one several questions (e.g. what is the MLFlow URL, which Neu.ro cluster should be considered, etc.). Alternatively, one might also set the following env vars:
    - `M2S_MLFLOW_HOST` - MLFlow server host name (example: _https://mlflow--user.jobs.cluster.org.neu.ro_)/;
    - `M2S_MLFLOW_STORAGE_ROOT` - artifact root path in the platform storage (_storage:myproject/mlruns_);
    - `M2S_SELDON_NEURO_DEF_IMAGE` - docker image, stored in a platform registry, which will be used to deploy the model (_image:myproject/seldon:v1_). Alternatively, one might configure service to use another platform image for deployment by tagging the respective registerred model (not a model version (!) ) with the tag named after `M2S_MLFLOW_DEPLOY_IMG_TAG` chart parameter value (for instance, with a tag named "_deployment-image_" and the value "_image:myproject/seldon:v2_);
    - `M2S_SRC_NEURO_CLUSTER` - Neu.ro cluster, where deployment image, MLflow artifacts and MLFlow itself are hosted (_demo_cluster_);
- Direct use of the helm chart is possible, however less comfortable - all requested by makefile info should be passed as chart values.

## Cleanup 
- `make helm_delete` - will delete:
    - all created by this helm chart resources, required for this service and the service itself;
    - Kubernetes namespace (and as a result all the resources within it), where SeldonDeployments were creating (M2S_SELDON_DEPLOYMENT_NS);


# Got questions or suggestions?


Feel free to contact us via [:email:](mailto:mlops@neu.ro) or @ [slack](https://neuro-community.slack.com/).

Maintained by [Neu.ro](https://neu.ro) MLOps team with :heart:
