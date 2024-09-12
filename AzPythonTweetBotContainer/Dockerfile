FROM mcr.microsoft.com/azure-functions/python:4.35.1.2-python3.11-slim

ENV AzureWebJobsScriptRoot=/home/site/wwwroot 
ENV AzureFunctionsJobHost__Logging__Console__IsEnabled=true
ENV AzureWebJobsFeatureFlags=EnableWorkerIndexing


COPY requirements.txt /home/site/wwwroot/
RUN pip install -r /home/site/wwwroot/requirements.txt

COPY . /home/site/wwwroot