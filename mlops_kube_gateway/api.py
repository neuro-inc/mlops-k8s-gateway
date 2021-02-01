import urllib.request
import asyncio
import os
from dataclasses import dataclass

import yaml
import shlex
import argparse
import subprocess
import base64
import json
import logging
import tempfile
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict
from multiprocessing import Process

import aiohttp.web
from aiohttp.web import (
    HTTPOk,
    HTTPBadRequest,
    HTTPInternalServerError,
    Request,
    Response,
    StreamResponse,
    json_response,
    middleware,
)
from aiohttp.web_exceptions import HTTPCreated

logger = logging.getLogger(__name__)

def _load_json(url: str, **kwargs):
    return json.loads(urllib.request.urlopen(url, **kwargs).read())

async def _create_seldon_deployment(
    *,
    name: str,
    seldon_neuro_passed_config: str,
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
                "image": "neuromation/neuro-extras:latest",
                "imagePullPolicy": "Always",
                "command": ["bash", "-c"],
                "args": [f"neuro --verbose cp {model_storage_uri} /storage"],
                "volumeMounts": [
                    {"mountPath": "/storage", "name": "neuro-storage"},
                ],
                "securityContext":{
                    "runAsUser": 0,
                },
                "env": [
                    {
                        "name": "NEURO_PASSED_CONFIG",
                        "value": seldon_neuro_passed_config,
                    }
                ],
            }
        ],
        "containers": [
            {
                "name": "model",
                "image": model_image_ref,
                "imagePullPolicy": "Always",
                "volumeMounts": [
                    {"mountPath": "/storage", "name": "neuro-storage"}
                ],
            }
        ],
    }
    # TODO: when using minio, deploy directly from MLFlow:
    #  https://docs.seldon.io/projects/seldon-core/en/v1.1.0/servers/mlflow.html#examples
    return {
        "apiVersion": "machinelearning.seldon.io/v1",
        "kind": "SeldonDeployment",
        "metadata": {"name": name, "namespace": "seldon"},
        "spec": {
            "predictors": [
                {
                    "componentSpecs": [{"spec": pod_spec}],
                    "graph": {
                        "endpoint": {"type": "REST"},
                        "name": "model",
                        "type": "MODEL",
                    },
                    "name": "predictor",
                    "replicas": 1,
                }
            ]
        },
    }


def _full_neuro_image_to_ref(image_uri: str) -> str:
    pre = "image://"
    if not image_uri.startswith(pre):
        raise ValueError(f"Invalid neuro image: expected '{pre}...' got '{image_uri}'")
    image_uri = image_uri[len(pre): ]
    cluster, user, *rest = image_uri.split("/")
    return f"registry.{cluster}.org.neu.ro/{user}/" + "/".join(rest)


def _parse_cluster_name(storage_uri: str) -> str:
    pre = "storage://"
    if not storage_uri.startswith(pre):
        raise ValueError(f"Invalid neuro storage: expected '{pre}...' got '{storage_uri}'")
    storage_uri = storage_uri[len(pre): ]
    cluster, user, *rest = storage_uri.split("/")
    return cluster


async def poll_mlflow(env):
    env = {
        k: v
        for k, v in env.items()
        if k.startswith("MKG_")
    }
    env_str = "\n".join((f"{k}={v}" for k, v in env.items()))
    logger.info(f"Environment:\n{env_str}")

    # Settings of the first cluster where MLflow is deployed (neuro-compute):
    mlflow_neuro_user = env["MKG_MLFLOW_NEURO_USER"]
    mlflow_neuro_cp_token = env["MKG_MLFLOW_NEURO_CP_TOKEN"]
    mlflow_neuro_job_name = env["MKG_MLFLOW_NEURO_JOB_NAME"]
    mlflow_neuro_project_storage = env["MKG_MLFLOW_NEURO_PROJECT_STORAGE"]
    mlflow_neuro_cluster = _parse_cluster_name(mlflow_neuro_project_storage)
    mlflow_uri_base = f"https://{mlflow_neuro_job_name}--{mlflow_neuro_user}.jobs.{mlflow_neuro_cluster}.org.neu.ro"
    mlflow_url = mlflow_uri_base + "/api/2.0/preview/mlflow"
    seldon_neuro_passed_config = base64.b64encode(
        json.dumps(
            {
                "token": mlflow_neuro_cp_token,
                "cluster": mlflow_neuro_cluster,
                "url": "https://staging.neu.ro/api/v1",
            }
        ).encode()
    ).decode()

    # Settings of the second cluster where Seldon is deployed (onprem-poc):
    seldon_model_name = env.get("MKG_SELDON_MODEL_NAME", "my-model")
    seldon_model_stage = env.get("MKG_SELDON_MODEL_STAGE", "Production")
    seldon_model_file_name = env.get("MKG_SELDON_MODEL_FILE_NAME", "model.pth")
    seldon_neuro_registry_secret_name = env.get("MKG_SELDON_NEURO_REGISTRY_SECRET_NAME", "neuro-registry")
    seldon_neuro_image = env.get("MKG_SELDON_NEURO_IMAGE", f"image://onprem-poc/artemyushkovsky/ml_recipe_bone_age/seldon:21.1.23")
    seldon_neuro_image_ref = _full_neuro_image_to_ref(seldon_neuro_image)

    DELAY = 5

    prev_version = None
    model_versions_uri = f"{mlflow_url}/registered-models/get-latest-versions?name={seldon_model_name}&stages={seldon_model_stage}"
    logger.info(f"Starting polling {model_versions_uri} with delay {DELAY} sec")
    while True:
        try:
            async with aiohttp.ClientSession() as session:
                await asyncio.sleep(DELAY)
                logger.info(f"Polling {mlflow_uri_base}: model '{seldon_model_name}' stage '{seldon_model_stage}'")
                async with session.get(model_versions_uri) as resp:
                    assert resp.status == 200, (resp.status, await resp.text())
                    data = await resp.json()
                    model_metadata = data["model_versions"][0]
                    model_version = model_metadata["version"]
                    if prev_version is None or model_version != prev_version:
                        logger.info("")
                        logger.info(f"Deploying model version={model_version}")
                        logger.info(f"Model metadata:\n{yaml.dump(model_metadata)}")
                        try:
                            run_id = model_metadata["run_id"]
                            model_metrics_uri = f"{mlflow_url}/runs/get?run_id={run_id}"
                            async with session.get(model_metrics_uri) as r:
                                assert r.status == 200, (r.status, await r.text())
                                metrics_data = await r.json()
                                metrics_data = metrics_data["run"]

                                run_info = metrics_data["info"]
                                logger.info(f"Model run info:\n{yaml.dump(run_info)}")

                                # model_params = metrics_data["data"]["params"]
                                # logger.info(f"Model params:\n{yaml.dump(model_params)}")

                                model_metrics = metrics_data["data"]["metrics"]
                                logger.info(f"Model metrics:\n{yaml.dump(model_metrics)}")
                        except asyncio.CancelledError:
                            raise
                        except BaseException as e:
                            logger.warning(f"Could not get model metrics: {e}")

                        logger.info(f"Model")
                        model_source = model_metadata['source']
                        assert model_source.startswith('/usr/local/share/'), model_source
                        assert model_source.endswith('/artifacts/model'), model_source
                        model_subpath = model_source[len('/usr/local/share/'):]
                        model_storage_uri = f"{mlflow_neuro_project_storage}/{model_subpath}/data/{seldon_model_file_name}"
                        deployment_json = await _create_seldon_deployment(
                            name=seldon_model_name,
                            seldon_neuro_passed_config=seldon_neuro_passed_config,
                            registry_secret_name=seldon_neuro_registry_secret_name,
                            model_image_ref=seldon_neuro_image_ref,
                            model_storage_uri=model_storage_uri,
                        )
                        deployment = yaml.dump(deployment_json)
                        # logger.info(f"Creating:\n{deployment}")
                        path = Path(tempfile.mktemp())
                        path.write_text(deployment)
                        subprocess.run(f"kubectl apply -f {path}", shell=True, check=True)
                        prev_version = model_version
                        logger.info(f"Model version={model_version} successfully deployed!")
                    # else:
                    #     logger.info(f"Found same version: {model_version}")

        except asyncio.CancelledError:
            pass
        except BaseException as e:
            logger.warning(f"Unexpected exception (ignoring): {e}")
        finally:
            # logger.info(f"Deleting seldon deployment {seldon_model_name}...")
            # subprocess.run(f"kubectl -n seldon delete {seldon_model_name}", shell=True, check=True)
            # logger.info(f"Deleted")
            pass

def main():
    logging.basicConfig(level=logging.DEBUG, 
                        format='%(asctime)s %(levelname)s %(message)s',
                        datefmt='%Y-%m-%d %H:%M:%S')
    asyncio.run(poll_mlflow(os.environ))
