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

5. Duplicate folder `workspace/example_secrets` and rename it to `workspace/secrets`. Setup `workspace/secrets/dev_app_secrets.yml` to add secrets in your environment variable. Please reach out to Kelvin to get these secrets.

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

The CI/CD pipeline consists of 4 environments:

- dev(local machine) - The environment for your local development.
- lat(latest) - The environment automatically built on the HEAD of `main` branch.
- stg(staging) - The environment for internal testing and validation.
- prd(production) - The environment to serve live customer traffic.

### Endpoints

| stages | app                                                                | api (Load Balancer)                                                    | api (API Gateway)                                               |
| ------ | ------------------------------------------------------------------ | ---------------------------------------------------------------------- | --------------------------------------------------------------- |
| dev    | http://localhost:8501/                                             | http://localhost:8000/docs                                             | -                                                               |
| lat    | http://pal-mono-lat-app-lb-1258791823.us-west-1.elb.amazonaws.com/ | http://pal-mono-lat-api-lb-1443082111.us-west-1.elb.amazonaws.com/docs | https://b1rdkt5cpa.execute-api.us-west-1.amazonaws.com/lat/docs |
| stg    | http://pal-mono-stg-app-lb-1654020856.us-west-1.elb.amazonaws.com/ | http://pal-mono-stg-api-lb-1164693723.us-west-1.elb.amazonaws.com/docs | https://b1rdkt5cpa.execute-api.us-west-1.amazonaws.com/stg/docs |
| prd    | http://pal-mono-prd-app-lb-270235957.us-west-1.elb.amazonaws.com/  | http://pal-mono-prd-api-lb-222574634.us-west-1.elb.amazonaws.com/docs  | https://b1rdkt5cpa.execute-api.us-west-1.amazonaws.com/prd/docs |
