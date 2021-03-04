from __future__ import annotations
import os
import logging
import tempfile
import yaml
import subprocess
import asyncio
import urllib.request
from pathlib import Path
from dataclasses import dataclass
from typing import Any, Dict, Mapping

from yarl import URL
from neuro_sdk import Factory, Client, Storage
from mlflow.tracking.client import MlflowClient
from mlflow.entities.model_registry import ModelVersion, RegisteredModel


DELAY = 2
# caution: it's hardcoded also into roles at ..k8s/seldon-roles.yaml
DEFAULT_DEPLOYMENT_NAMESPACE = "seldon"
# caution: it's hardcoded also into roles at ..k8s/seldon-roles.yaml
DEFAULT_REG_SECRET_NAME = "neuro-registry"


@dataclass
class _DeployedModel:
    image: str
    model_file: str
    model_name: str
    model_storage_uri: URL
    model_stage: str
    model_version: str
    source_run_id: str
    need_redeploy: bool = False

    def is_same_version(self, other: _DeployedModel) -> bool:
        return self.name == other.name and self.model_version == other.model_version

    @property
    def name(self) -> str:
        return f"{self.model_stage}/{self.model_name}"


async def poll_mlflow(env):

    # Settings of the source cluster, where MLflow is deployed:
    mlflow_neuro_token = env["M2S_MLFLOW_NEURO_TOKEN"]
    mlflow_storage_root = env["M2S_MLFLOW_STORAGE_ROOT"]
    mlflow_host = env["M2S_MLFLOW_HOST"]
    image_base_name = env["M2S_SELDON_NEURO_IMG_BASE_NAME"]
    neuro_reg_secret = env.get("M2S_NEURO_REGISTRY_SECRET", DEFAULT_REG_SECRET_NAME)

    client_factory = Factory()
    await client_factory.login_with_token(source_neuro_token)
    neuro_client = await client_factory.get()
    mlflow_client = MlflowClient(tracking_uri=source_mlflow_host)

    image_base_ref = neuro_client.parse.remote_image(image_base_name).as_docker_url()
    image_base_ref = image_base_ref[: image_base_ref.index(":")]  # drop :latest tag

    seldon_models: Mapping[str, _DeployedModel] = dict()
    mlflow_models: Mapping[str, _DeployedModel] = dict()
    while True:
        logging.info(f"Polling {source_mlflow_host}")
        try:
            # fetch current state of MLFlow
            for model in mlflow_client.search_registered_models():
                for model_version in model.latest_versions:
                    if model_version.current_stage == "None":
                        # model version is not in "staging" nor in "production" stages
                        continue
                    # mlflow-config related path, e.g.
                    # ('/', 'usr', 'local', 'share', 'mlruns', '0', 'ae72265a0a17473f993f78ab239c2f2f', 'artifacts', 'model')
                    source_path_parts = Path(model_version.source).parts
                    # leave pure mlflow subpath, e.g.: ('0', 'ae72265a0a17473f993f78ab239c2f2f', 'artifacts', 'model')
                    mlflow_source_parts = source_path_parts[
                        source_path_parts.index(model_version.run_id) - 1 :
                    ]
                    storage_art_uri = URL(
                        f"{mlflow_storage_root}/{'/'.join(mlflow_source_parts)}"
                    )
                    registered_model = _DeployedModel(
                        image=f"{image_base_ref}/{model.name}:latest",  # TODO: give abbility to fetch image url from tags?
                        model_storage_uri=storage_art_uri,
                        model_name=model.name,
                        model_stage=model_version.current_stage,
                        model_version=model_version.version,
                        source_run_id=model_version.run_id,
                    )
                    deployed_model = seldon_models.get(registered_model.name)
                    if not deployed_model or not deployed_model.is_same_version(
                        registered_model
                    ):
                        registered_model.need_redeploy = True
                        mlflow_models[registered_model.name] = registered_model

            # deploy models in Seldon
            for model_name in mlflow_models.keys():
                if mlflow_models[model_name].need_redeploy:
                    _deploy_model(
                        mlflow_models[model_name],
                        neuro_client,
                        neuro_reg_secret,
                    )

            # removing outdated models
            for model_name in set(seldon_models.keys()) - set(mlflow_models.keys()):
                _delete_seldon_deployment(model_name)

            # the state is sync
            seldon_models = mlflow_models.copy()
            asyncio.sleep(DELAY)  # not to overload an API

        except BaseException as e:
            logging.warning(f"Unexpected exception (ignoring): {e}")
        finally:
            for model_name in seldon_models.keys():
                _delete_seldon_deployment(model_name)


async def _deploy_model(
    model: _DeployedModel, neuro_client: Client, neuro_reg_secret: str
) -> None:
    logging.info("")
    logging.info(f"Deploying model: {model}")

    neuro_token = await neuro_client.config.token()
    deployment_json = _create_seldon_deployment(
        name=model.model_name,
        neuro_login_token=neuro_token,
        registry_secret_name=neuro_reg_secret,
        model_image_ref=model.image,
        model_storage_uri=str(model.model_storage_uri),
    )
    deployment = yaml.dump(deployment_json)
    path = Path(tempfile.mktemp())
    path.write_text(deployment)
    subprocess.run(f"kubectl apply -f {path}", shell=True, check=True)
    logging.info(f"Successfully deployed model: {model}")


def _create_seldon_deployment(
    *,
    name: str,
    neuro_login_token: str,
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
                "name": "neuro-download",
                "image": "neuromation/neuro-extras:20.12.16",
                "imagePullPolicy": "Always",
                "command": ["bash", "-c"],
                "args": [
                    f"neuro config login-with-token $NEURO_LOGIN_TOKEN",
                    f"neuro --verbose cp -r -T {model_storage_uri} /storage",
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
                "name": "model",
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
        "metadata": {"name": name, "namespace": DEFAULT_DEPLOYMENT_NAMESPACE},
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


def _delete_seldon_deployment(name: str) -> bool:
    logging.info(f"Deleting '{name}' model deployment.")
    try:
        subprocess.run(
            f"kubectl -n {DEFAULT_DEPLOYMENT_NAMESPACE} delete SeldonDeployment {name}",
            shell=True,
            check=True,
        )
        logging.info(f"Successfully deleted '{name}' model deployment.")
        return True
    except subprocess.CalledProcessError as e:
        logging.error(
            "Unable to delete SeldonDeployment '{name}' in '{DEFAULT_DEPLOYMENT_NAMESPACE}' namespace: {e}"
        )
        return False


def main():
    env = {k: v for k, v in env.items() if k.startswith("M2S_")}
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    asyncio.run(poll_mlflow(env))
