#FROM python:3.7
#
## Install code
#COPY platform_integrations /opt/platform_integrations
#RUN pip install -U pip \
#    && pip install -e /opt/platform_integrations
#
## Install kubectl
#RUN cd /tmp \
#    && curl -LO https://storage.googleapis.com/kubernetes-release/release/v1.20.1/bin/linux/amd64/kubectl \
#    && chmod +x ./kubectl \
#    && mv ./kubectl /usr/local/bin/kubectl \
#    && kubectl version --client
#
### Install neuro clis
##RUN pip install -U \
##    neuro-cli==20.12.16 \
##    neuro-extras==20.12.16
#
#
#ENV NP_INTEGRATIONS_API_PORT=8080
#EXPOSE $NP_INTEGRATIONS_API_PORT
#
#CMD platform-integrations
