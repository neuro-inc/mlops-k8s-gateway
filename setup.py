from setuptools import find_packages, setup

install_requires = (
    "aiohttp==3.7.2",
    "PyYAML==5.3.1",
    # "neuro_auth_client==19.10.5",
    # "platform_config_client==20.11.26",
    # "neuromation==20.12.7",
    # "trafaret==2.1.0",
    # "platform-logging==0.3",
    # "aiohttp-cors==0.7.0",
    # "aiobotocore==1.1.2",
    # "urllib3>=1.20,<1.26",  # botocore requirements
)

setup(
    name="mlops-kube-gateway",
    version="0.0.0",
    url="https://github.com/neuro-inc/mlops-kube-gateway",
    packages=find_packages(),
    install_requires=install_requires,
    python_requires=">=3.7",
    entry_points={
        "console_scripts": ["mlops-kube-gateway=mlops_kube_gateway.api:main"]
    },
)
