# pal-mono
[![Pre commit](https://github.com/Proactive-AI-Lab/pal-mono/actions/workflows/precommit.yml/badge.svg)](https://github.com/Proactive-AI-Lab/pal-mono/actions/workflows/precommit.yml) 
[![Create build](https://github.com/Proactive-AI-Lab/pal-mono/actions/workflows/create-build.yml/badge.svg)](https://github.com/Proactive-AI-Lab/pal-mono/actions/workflows/create-build.yml) 
[![Create release](https://github.com/Proactive-AI-Lab/pal-mono/actions/workflows/create-release.yml/badge.svg)](https://github.com/Proactive-AI-Lab/pal-mono/actions/workflows/create-release.yml)

## Overview

This is our main monolith service. It is a Python service that serves 2 artifacts:

- api - a RESTful API that serves the main functionality of the service

- app - a web app that demos the functionalities of the service

## Development

Follow the next steps to run the pal-mono service on your local computer.

1. Make sure Python v3.11, Pip3 and Docker are installed on your Mac.
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

5. Create a new file named `workspace/secrets/dev_app_secrets.yml` to add environment variable. Please refer to this [doc](https://docs.google.com/document/d/1-P-R0bRgnrss0oVUE6O1vX8Tu3HaMLSGG52T04bkz1s) to get these secrets.

6. Build and run both API and web app locally

```bash
phi ws up

phi ws up -f (Force rebuild from scratch)
```

7. [One-time] Log into the internal app at http://localhost:8501/. Under the 'Onboarding' page, enter account name "proactiveailab" (other fields can be left blank), and click 'Create Account' button. 

8. [One-time] Go to the 'Projects' page, and add this row into the 'Project Update' table:

| Channel  | Identifier |
|----------|----------|
| internal_app    | proactiveailab-default  |

9. Under the 'Live' page, you should be able to talk to the agent of "proactiveailab" account.


### Local Environment
`phi ws up` will automatically spin up new Docker containers that install dependencies in `requirements.txt` that enable `pal-mono` to function. The dependencies are specified in `pyproject.toml` and updates to `requirements.txt` are made with `./scripts/upgrade.sh`.

Since PhiData installs these dependencies in the Docker container environment, our local environment (e.g. VS Code) will not recognize the missing imports. To set up the local environment:

```bash
./scripts/install.sh
```

### Channel Configurations
To open up channels (eg. internal app's live page, api) to talk to a local agent, they need to be configured. In the Channel:Identifier table under the projects page, save the following rows for each account.
| Channel  | Identifier |
|----------|----------|
| internal_app    | <project_name>   |
| api    | <project_name>   |

For example,

| Channel  | Identifier |
|----------|----------|
| internal_app    | proactiveailab-default  |
| api    | proactiveailab-default   |


## Others

1. You can read the API documentation running in your local host http://localhost:8000/docs#/. and the web app running in your local host http://localhost:8501/.

2. You can install this Visual Studio extension to run the Python Lint check in your IDE while you code: https://marketplace.visualstudio.com/items?itemName=charliermarsh.ruff

3. You can install this Visual Studio Python Debugger extension to Debug the Python code in your IDE while you code: https://marketplace.visualstudio.com/items?itemName=ms-python.debugpy. We have a launch.json file in the .vscode folder that you can use to debug our cli_playground.py file in your IDE.

## Validation

We use several tools to ensure code quality and consistency. These tools are run automatically before every commit.

- Format with `black .`
- Sort imports with `isort .`
- Lint with `ruff check . --fix`
- Type check with `pyright .`


Run the following command to validate your code locally:

```bash
./scripts/validate.sh
```

## CI/CD

### Testing
Testing is done with [pytest](https://docs.pytest.org/en/7.1.x/contents.html), which runs all tests named test_* in files named test_*.py or *_test.py. Test files should be placed in the same directory as the source file.

To run, first start the containers.
```
phi ws up
```
Then run the test script.
```
./scripts/test.sh
```

### Environments

The CI/CD pipeline consists of 4 environments:

- dev(local machine) - The environment for your local development.
- lat(latest) - The environment automatically built on the HEAD of `main` branch.
- stg(staging) - The environment for internal testing and validation.
- prd(production) - The environment to serve live customer traffic.

### Endpoints

| stages | app                                                                | api                                                     |  api docs (internal)                                        |
| ------ | ------------------------------------------------------------------ | ---------------------------------------------------------------------- | --------------------------------------------------------------- |
| dev    | http://localhost:8501/                                             | http://localhost:8000/                                             | http://localhost:8000/docs                                                               |
| lat    | http://pal-mono-lat-app-lb-1258791823.us-west-1.elb.amazonaws.com/ | https://b1rdkt5cpa.execute-api.us-west-1.amazonaws.com/lat |http://pal-mono-lat-api-lb-1443082111.us-west-1.elb.amazonaws.com/docs  |
| stg    | http://pal-mono-stg-app-lb-1654020856.us-west-1.elb.amazonaws.com/ | https://b1rdkt5cpa.execute-api.us-west-1.amazonaws.com/stg | http://pal-mono-stg-api-lb-1164693723.us-west-1.elb.amazonaws.com/docs |
| prd    | http://pal-mono-prd-app-lb-270235957.us-west-1.elb.amazonaws.com/  | https://b1rdkt5cpa.execute-api.us-west-1.amazonaws.com/prd  | http://pal-mono-prd-api-lb-222574634.us-west-1.elb.amazonaws.com/docs |
