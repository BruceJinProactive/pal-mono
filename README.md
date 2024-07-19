# pal-mono

## Overview

This is our main monolith service. It is a Python service that serves 2 artifacts:

- api - a RESTful API that serves the main functionality of the service

- app - a web app that demos the functionalities of the service

## Development

Follow the next steps to run the pal-mono service on your local computer.

1. Make sure Python3 (3.11 recommended), Pip3 and Docker are installed on your Mac.
2. Checkout the repo and navigate to the root folder.
3. Create a python virtual environment

```bash
python3 -m venv ~/.venvs/aienv
source ~/.venvs/aienv/bin/activate
```

4. [One-time] Install dependencies

```bash
pip3 install docker
pip3 install -U phidata
phi init
phi ws setup
```

5. Setup OpenAI API key in your environment variable

```bash
export OPENAI_API_KEY=sk-***
export LEPTON_API_KEY=***
export MODAL_API_KEY=***
```

6. Build and run both API and web app locally

```bash
phi ws up
```

7. You can read the API documentation running in your local host http://localhost:8000/docs#/. and the web app running in your local host http://localhost:8501/.

8. You can install this Visual Studio extension to run the Python Lint check in your IDE while you code: https://marketplace.visualstudio.com/items?itemName=charliermarsh.ruff

9. You can install this Visual Studio Python Debugger extension to Debug the Python code in your IDE while you code: https://marketplace.visualstudio.com/items?itemName=ms-python.debugpy. We have a launch.json file in the .vscode folder that you can use to debug our cli_playground.py file in your IDE.

## Validation

We use several tools to ensure code quality and consistency. These tools are run automatically before every commit.

- Format with `black .`
- Sort imports with `isort .`
- Lint with `ruff check .`
- Type check with `mypy .`

[One-time] Install the following tools locally:

```bash
pip3 install black isort ruff mypy
```

Run the following command to validate your code locally:

```bash
./scripts/validate.sh
```

## CI/CD

### Environments

The CI/CD pipeline is divided into 3 stages:

- dev(your local development) - The environment for your local development. Changes before merged into `main` branch.
- stg(staging) - The environment for internal testing and validation. Changes on the HEAD of `main` branch, before merged into `prd` branch.
- prd(production) - The environment to serve live customer traffic. Changes on `prd` branch.

### Releasing from `dev` to `stg`:

1. If you need to use any new env variables, please let @max or @kelvin know so they can add them to the AWS config
2. Create a feature branch `example-feature` based from `main` and make changes locally.
3. Make a pull request merging `example-feature` to `main`.
4. Wait for PR review and approval.
5. Submit the PR to merge `example-feature` to `main`.
6. A staging release will be automatically triggered. Join Slack channel #cicd-notifications to receive notifications.

### Releasing from `stg` to `prd`:

[TODO] The process is manual for now.

1. If you need to use any new env variables, please let @max or @kelvin know so they can add them to the AWS config
2. Make a pull request merging `main` to `prd`.
3. Wait for PR review and approval.
4. Submit the PR to merge `main` to `prd`.
5. A release release will be automatically triggered. Join Slack channel #cicd-notifications to receive notifications.

## Endpoints

|     | app                                                                | api (Load Balancer)                                                | api (API Gateway)                                              |
| --- | ------------------------------------------------------------------ | ------------------------------------------------------------------ | -------------------------------------------------------------- |
| stg | http://pal-mono-stg-app-lb-1654020856.us-west-1.elb.amazonaws.com/ | http://pal-mono-stg-api-lb-1164693723.us-west-1.elb.amazonaws.com/ | https://5xtuyf38b8.execute-api.us-west-1.amazonaws.com/stg-api |
| prd | http://pal-mono-prd-app-lb-270235957.us-west-1.elb.amazonaws.com/  | http://pal-mono-prd-api-lb-222574634.us-west-1.elb.amazonaws.com/  | https://5xtuyf38b8.execute-api.us-west-1.amazonaws.com/api     |
