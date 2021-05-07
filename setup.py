from setuptools import find_packages, setup

install_requires = (
    "PyYAML==5.3.1",
    "neuro-sdk==21.4.23",
    "neuro-flow==21.3.19",
    "mlflow==1.14.0",
    "yarl==1.6.3",
)

setup(
    name="neuro-mlflow2seldon",
    version="0.0.1",
    url="https://github.com/neuro-inc/mlops-k8s-mlflow2seldon",
    packages=find_packages(),
    install_requires=install_requires,
    python_requires=">=3.7",
    entry_points={"console_scripts": ["mlflow2seldon=mlflow2seldon.api:main"]},
)
