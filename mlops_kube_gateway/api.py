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
    neuro_passed_config: str,
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
                "args": [f"neuro cp {model_storage_uri} /storage"],
                "volumeMounts": [
                    {"mountPath": "/storage", "name": "neuro-storage"},
                ],
                "securityContext":{
                    "runAsUser": 0,
                },
                "env": [
                    {
                        "name": "NEURO_PASSED_CONFIG",
                        "value": neuro_passed_config,
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

async def poll_mlflow(env):
    env = {
        k: v
        for k, v in env.items()
        if k.startswith("MKG_")
    }
    env_str = "\n".join((f"{k}={v}" for k, v in env.items()))
    logger.info(f"Environment:\n{env_str}")

    neuro_cp_token = env["MKG_NEURO_CP_TOKEN"]
    project_name = env["MKG_NEURO_PROJECT_NAME"]

    model_name = env.get("MKG_SELDON_MODEL_NAME", "my-model")
    model_stage = env.get("MKG_SELDON_MODEL_STAGE", "Production")

    mlflow_uri_base = env.get("MKG_MLFLOW_URI", "https://open-source-stack-mlflow-server--yevheniisemendiak.jobs.neuro-compute.org.neu.ro")
    neuro_model_image_ref = env.get("MKG_NEURO_MODEL_IMAGE_REF", "registry.onprem-poc.org.neu.ro/yevheniisemendiak/startup_package_test/seldon:20.12.16")
    neuro_cluster = env.get("MKG_NEURO_CLUSTER", "neuro-compute")
    neuro_user = env.get("MKG_NEURO_USER", "yevheniisemendiak")

    neuro_passed_config = base64.b64encode(
        json.dumps(
            {
                "token": neuro_cp_token,
                "cluster": "neuro-compute",
                "url": "https://staging.neu.ro/api/v1",
            }
        ).encode()
    ).decode()

    mlflow_url = mlflow_uri_base + "/api/2.0/preview/mlflow"

    delay = 1

    prev_version = None
    model_versions_uri = f"{mlflow_url}/registered-models/get-latest-versions?name={model_name}&stages={model_stage}"
    logger.info(f"Starting polling {model_versions_uri} with delay {delay} sec")
    while True:
        try:
            async with aiohttp.ClientSession() as session:
                await asyncio.sleep(delay)
                logger.info(f"Polling model {model_name} stage {model_stage}")
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

                                model_params = metrics_data["data"]["params"]
                                logger.info(f"Model params:\n{yaml.dump(model_params)}")

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
                        model_storage_uri = f"storage://{neuro_cluster}/{neuro_user}/{project_name}/{model_subpath}/data/model.h5"

                        deployment_json = await _create_seldon_deployment(
                            name=model_name,
                            neuro_passed_config=neuro_passed_config,
                            registry_secret_name="neuro-registry",
                            model_image_ref=neuro_model_image_ref,
                            model_storage_uri=model_storage_uri,
                        )
                        deployment = yaml.dump(deployment_json)
                        # logger.info(f"Creating:\n{deployment}")
                        path = Path(tempfile.mktemp())
                        path.write_text(deployment)
                        subprocess.run(f"kubectl apply -f {path}", shell=True, check=True)
                        # import asyncio.subprocess
                        # asyncio.subprocess.run(f"kubectl apply -f {path}", shell=True, check=True)
                        prev_version = model_version
                        # logger.info(f"Successfully deployed, from temp path {path}")
                    # else:
                    #     logger.info(f"Found same version: {model_version}")

        except asyncio.CancelledError:
            pass
        except BaseException as e:
            logger.warning(f"Unexpected exception (ignoring): {e}")
        finally:
            # logger.info(f"Deleting seldon deployment {model_name}...")
            # subprocess.run(f"kubectl -n seldon delete {model_name}", shell=True, check=True)
            # logger.info(f"Deleted")
            pass

def main():
    logging.basicConfig(level=logging.DEBUG, 
                        format='%(asctime)s %(levelname)s %(message)s')
    asyncio.run(poll_mlflow(os.environ))
