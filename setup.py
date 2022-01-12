from setuptools import find_packages, setup


install_requires = (
    "PyYAML >= 5.3.1",
    "neuro-sdk >= 22.1.0",
    "neuro-cli >= 22.1.0",
    "neuro-extras >= 21.11.5",
    "mlflow >= 1.14.0",
    "yarl >= 1.6.3",
    "click >= 7.1.2, <= 8.0.3",
)

setup(
    name="neuro-mlflow2seldon",
    version="0.0.2",
    url="https://github.com/neuro-inc/mlops-k8s-mlflow2seldon",
    packages=find_packages(),
    install_requires=install_requires,
    python_requires=">=3.9",
    entry_points={"console_scripts": ["mlflow2seldon=mlflow2seldon.api:main"]},
)
