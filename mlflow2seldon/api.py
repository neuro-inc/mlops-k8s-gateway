from __future__ import annotations
import os
import sys
import re
import signal
import logging
import tempfile
import yaml
import subprocess
import asyncio
from pathlib import Path
from dataclasses import dataclass
from typing import Any, Dict

from yarl import URL
from neuro_sdk import Factory, Client
from mlflow.tracking.client import MlflowClient


DELAY = 2
CLUSTER_FROM_JOB_URL_MASK = "jobs.(.*).org.neu.ro"


@dataclass
class _DeployedModel:
    image: str
    model_name: str
    model_storage_uri: URL
    model_stage: str
    model_version: str
    source_run_id: str
    deployment_namespace: str
    need_redeploy: bool = False

    def is_same_version(self, other: _DeployedModel) -> bool:
        all_is_true = all(
            (
                self.name == other.name,
                self.model_version == other.model_version,
            )
        )
        return all_is_true

    @property
    def name(self) -> str:
        return f"{self.model_name}-{self.model_stage}".lower()


async def poll_mlflow(env: Dict):

    # Settings of the source cluster, where MLflow is deployed:
    mlflow_storage_root = env["M2S_MLFLOW_STORAGE_ROOT"]
    mlflow_host = env["M2S_MLFLOW_HOST"]
    default_image = env["M2S_SELDON_NEURO_DEF_IMAGE"]
    deploy_image_tag = env["M2S_MLFLOW_DEPLOY_IMG_TAG"]
    registry_secret_name = env["M2S_NEURO_REGISTRY_SECRET"]
    seldon_deployment_ns = env["M2S_SELDON_DEPLOYMENT_NS"]

    client_factory = Factory()
    # Assumption: MLFlow is running in a platform job
    cluster = re.findall(CLUSTER_FROM_JOB_URL_MASK, mlflow_host)[0]
    neuro_client = await client_factory.get()
    await neuro_client.config.switch_cluster(cluster)
    mlflow_client = MlflowClient(tracking_uri=mlflow_host)
    # Assumption: Seldon deployment image is on a same cluster, where MLflow is running
    default_image_ref = neuro_client.parse.remote_image(default_image).as_docker_url()

    seldon_models: Dict[str, _DeployedModel] = dict()
    try:
        while True:
            mlflow_models: Dict[str, _DeployedModel] = dict()
            logging.info(f"Polling {mlflow_host}")
            try:
                # iterate over all registered models ("Models" tab in MLflow WebUI)
                for model in mlflow_client.search_registered_models():
                    deploy_image = model.tags.get(deploy_image_tag)
                    if deploy_image:
                        deploy_image_ref = neuro_client.parse.remote_image(
                            deploy_image
                        ).as_docker_url()
                    else:
                        deploy_image_ref = default_image_ref
                    for model_version in model.latest_versions:
                        if model_version.current_stage not in ("Staging", "Production"):
                            # we deploy only Staging and Production models
                            continue
                        # Assumption: artifact store in MLflow is platform storage
                        # mlflow-config related path, e.g.
                        # ('/', 'usr', 'local', 'share', 'mlruns', '0', 'ae72265a0a17473f993f78ab239c2f2f', 'artifacts', 'model')
                        source_path_parts = Path(model_version.source).parts
                        # leave pure mlflow subpath, e.g.:
                        # ('0', 'ae72265a0a17473f993f78ab239c2f2f', 'artifacts', 'model')
                        mlflow_source_parts = source_path_parts[
                            source_path_parts.index(model_version.run_id) - 1 :
                        ]
                        storage_art_uri = URL(
                            f"{mlflow_storage_root}/{'/'.join(mlflow_source_parts)}"
                        )
                        registered_model = _DeployedModel(
                            image=deploy_image_ref,
                            model_storage_uri=storage_art_uri,
                            model_name=model.name,
                            model_stage=model_version.current_stage,
                            model_version=model_version.version,
                            source_run_id=model_version.run_id,
                            deployment_namespace=seldon_deployment_ns,
                        )
                        deployed_model = seldon_models.get(registered_model.name)
                        if not deployed_model or not deployed_model.is_same_version(
                            registered_model
                        ):
                            registered_model.need_redeploy = True
                        else:
                            registered_model.need_redeploy = False
                        mlflow_models[registered_model.name] = registered_model

                # deploy models in Seldon
                for model_name in mlflow_models.keys():
                    if mlflow_models[model_name].need_redeploy:
                        await _deploy_model(
                            mlflow_models[model_name],
                            neuro_client,
                            registry_secret_name,
                        )
                        mlflow_models[model_name].need_redeploy = False

                # removing outdated models
                for model_name in set(seldon_models.keys()) - set(mlflow_models.keys()):
                    _delete_seldon_deployment(seldon_models[model_name])

                # the state is sync
                seldon_models = mlflow_models.copy()
                deployed_models = [
                    f"{n}:{m.model_version}" for n, m in seldon_models.items()
                ]
                logging.info(f"Deployed models: {';'.join(deployed_models)}")
                await asyncio.sleep(DELAY)  # not to overload an API

            except KeyboardInterrupt:
                logging.warning("Got keyboard interrupt, gracefully shutting down...")
                break
            except Exception as e:
                logging.warning(f"Unexpected exception (ignoring): {e}")
    finally:
        for model in seldon_models.values():
            _delete_seldon_deployment(model)


async def _deploy_model(
    model: _DeployedModel, neuro_client: Client, registry_secret_name: str
) -> None:
    logging.info(f"Deploying model: {model}")

    neuro_token = await neuro_client.config.token()
    deployment_json = _create_seldon_deployment(
        name=model.name,
        namespace=model.deployment_namespace,
        neuro_login_token=neuro_token,
        neuro_cluster=neuro_client.config.cluster_name,
        registry_secret_name=registry_secret_name,
        model_image_ref=model.image,
        model_storage_uri=str(model.model_storage_uri),
    )
    deployment = yaml.dump(deployment_json)
    path = Path(tempfile.mktemp())
    path.write_text(deployment)
    try:
        subprocess.run(f"kubectl apply -f {path}", shell=True, check=True)
        logging.info(f"Successfully deployed model: {model}")
    except subprocess.CalledProcessError as e:
        logging.error(f"Unable to deploy '{model}': {e}")


def _create_seldon_deployment(
    *,
    name: str,
    namespace: str,
    neuro_login_token: str,
    neuro_cluster: str,
    registry_secret_name: str,
    model_image_ref: str,
    model_storage_uri: str,
) -> Dict[str, Any]:

    pod_spec = {
        "volumes": [
            {"emptyDir": {}, "name": "neuro-storage"},
        ],
        "imagePullSecrets": [{"name": registry_secret_name}],
        "initContainers": [
            {
                "name": "model-binary-download",
                "image": "neuromation/neuro-extras:latest",
                "imagePullPolicy": "Always",
                "command": ["bash", "-c"],
                "args": [
                    f"neuro config login-with-token $NEURO_LOGIN_TOKEN; "
                    f"neuro config switch-cluster {neuro_cluster}; "
                    f"neuro --verbose cp -r -T {model_storage_uri} /storage"
                ],
                "volumeMounts": [
                    {"mountPath": "/storage", "name": "neuro-storage"},
                ],
                "securityContext": {
                    "runAsUser": 0,
                },
                "env": [
                    {
                        "name": "NEURO_LOGIN_TOKEN",
                        "value": neuro_login_token,
                    },
                ],
            }
        ],
        "containers": [
            {
                "name": name,
                "image": model_image_ref,
                "imagePullPolicy": "Always",
                "volumeMounts": [{"mountPath": "/storage", "name": "neuro-storage"}],
            }
        ],
    }
    # TODO: when using minio, deploy directly from MLFlow:
    #  https://docs.seldon.io/projects/seldon-core/en/v1.1.0/servers/mlflow.html#examples
    return {
        "apiVersion": "machinelearning.seldon.io/v1",
        "kind": "SeldonDeployment",
        "metadata": {"name": name, "namespace": namespace},
        "spec": {
            "predictors": [
                {
                    "componentSpecs": [{"spec": pod_spec}],
                    "graph": {
                        "endpoint": {"type": "REST"},
                        "name": name,
                        "type": "MODEL",
                    },
                    "name": "predictor",
                    "replicas": 1,
                }
            ]
        },
    }


def _delete_seldon_deployment(model: _DeployedModel) -> bool:
    logging.info(f"Deleting '{model}' model deployment.")
    try:
        cmd = (
            f"kubectl -n {model.deployment_namespace} delete "
            "SeldonDeployment {model.name}",
        )
        subprocess.run(cmd, shell=True, check=True)
        logging.info(f"Successfully deleted '{model}' model deployment.")
        return True
    except subprocess.CalledProcessError as e:
        logging.error(f"Unable to delete SeldonDeployment '{model}': {e}")
        return False


def sigterm_handler(_signo, _stack_frame):
    logging.warning(f"Got SIGTERM({_signo}) signal, shutting down gracefully...")
    # Otherwise 'finally' block will not be triggered
    sys.exit(0)


def main():
    env = {k: v for k, v in os.environ.items() if k.startswith("M2S_")}
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    signal.signal(signal.SIGTERM, sigterm_handler)
    asyncio.run(poll_mlflow(env))
