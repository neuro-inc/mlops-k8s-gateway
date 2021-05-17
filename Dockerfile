FROM python:3.9

RUN curl --output /usr/local/bin/kubectl -L \
    https://storage.googleapis.com/kubernetes-release/release/v1.20.1/bin/linux/amd64/kubectl && \
    chmod +x /usr/local/bin/kubectl;

# package version is to be overloaded with exact version
WORKDIR /app
COPY . /app

RUN pip install -e .
