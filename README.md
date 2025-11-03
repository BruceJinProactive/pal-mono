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

1. Make sure Python v3.11, Node.js, Pip3, and Docker are installed on your Mac.
```bash
brew install python@3.11
brew install node
brew install --cask docker
```
Optionally install brew if not installed.
```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```
2. Check out the repo and navigate to the root folder.
3. Create a Python virtual environment.

```bash
python3 -m venv ~/.venvs/aienv
source ~/.venvs/aienv/bin/activate
```

4. [One-time] Install dependencies and Agno workspace setup.

```bash
./scripts/install.sh

# create agno workspace
ag init
ag ws setup
```

5. Create a new file named `workspace/secrets/dev_app_secrets.yml` to add environment variables. Please refer to this [doc](https://docs.google.com/document/d/1-P-R0bRgnrss0oVUE6O1vX8Tu3HaMLSGG52T04bkz1s) to get these secrets.
```bash
mkdir -p workspace/secrets && touch workspace/secrets/dev_app_secrets.yml
```

6. Build and run both API and web app locally.

```bash
ag ws up -y # appending -y allows you to skip the confirmation step

ag ws up -f (Force rebuild from scratch)
```

7. Run this command to migrate local db to the latest schema.

```bash
docker exec -it pal-mono-api alembic -c db/alembic.ini upgrade head
```

8. Getting Started with pal-manage-app

   - Clone the repo `pal-manage-app` and build it.
   - Create .env.local and fill in all required environment variables as instructed,
   - Run the following commands to start the development server:
     ```
     pnpm install
     pnpm dev
     ```
   - Run Manage app locally and navigate to http://localhost:3000/.

9. Log into the Management Application

   - In the top right corner of the page, click on Onboard. 
   - Enter the account name and account display name: "palona".

10. Create a New Agent

   - Enter the agent name: "palona agent".
   - Select the desired Agent Type and Language.
   - Select any desired Agent Personality Tags.

11. Create a New Project

    - Enter the project name: "palona-default".
    - Click on Create Account
    - Setup process is now complete

12. Under the 'Chat' page, you should be able to talk to the agent of the "palona" account.

### Local Environment

`ag ws up` will automatically spin up new Docker containers that install dependencies in `requirements.txt` that enable `pal-mono` to function. The dependencies are specified in `pyproject.toml` and updates to `requirements.txt` are made with `./scripts/upgrade.sh`.

Since Agno installs these dependencies in the Docker container environment, our local environment (e.g. VS Code) will not recognize the missing imports. To set up the local environment:

```bash
./scripts/install.sh
```

### Database Migration

After making changes to the db model, run this command to generate a revision file.
Note if you don't generate the revision file, the changes you made to the database model python files will diverge from the actual database schema in RDS.

```commandline
docker exec -it pal-mono-api alembic -c db/alembic.ini revision --autogenerate -m "<db-change-message>" # replace with a meaningful yet short message
```

Run the upgrade command below to bring your local database schema up to date:

```commandline
docker exec -it pal-mono-api alembic -c db/alembic.ini upgrade head
```

If later you want to modify the model again, the easiest way is to create another migration file for it. It's straightforward, but you are left with two revision files.
If you prefer to have only one revision file, you can delete the old revision file and just generate a new one. But if you've already upgraded to the latest schema locally, you have to downgrade the db before regenerating
a new revision. That can be done by this command:

```commandline
docker exec -it pal-mono-api alembic -c db/alembic.ini downgrade -1
```

### Channel Configurations

To enable communication channels (e.g., the Manage App’s chat page) for a local agent, the following configuration is required:

- Navigate to the Projects Page. In the sidebar, click Projects.
- Scroll to the Phone Number Management section on the Projects page.
- Reserve a phone number for the desired communication channel(s), such as Voice or SMS.

## Managing Data

### PSQL Connection

You can connect to the docker postgres instance directly via

```commandline
psql -h localhost -U app
```

Password is **_app_**

## Others

1. You can read the API documentation running on your local host: [http://localhost:8000/docs#/](http://localhost:8000/docs#/)

2. You can install this [Visual Studio extension](https://marketplace.visualstudio.com/items?itemName=charliermarsh.ruff) to run the Python lint check in your IDE while you code.

3. You can install this [Visual Studio Python debugger extension](https://marketplace.visualstudio.com/items?itemName=ms-python.debugpy) to debug the Python code in your IDE while you code. We have a launch.json file in the .vscode folder that you can use to debug our cli_playground.py file in your IDE.

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

Testing is done with [pytest](https://docs.pytest.org/en/7.1.x/contents.html), which runs all tests named test*\* in files named test*_.py or _\_test.py. Test files should be placed in the same directory as the source file.

To run, first start the containers.

```
ag ws up
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

Endpoints are hosted in dedicated AWS accounts: `lat`, `stg`, and `prd`.

| env | manage app                       | admin console                  | api                        |
| --- | -------------------------------- | ------------------------------ | -------------------------- |
| dev | http://localhost:3000/           | http://localhost:8501/         | http://localhost:8000/     |
| lat | http://lat-manage-app.palona.ai/ | https://lat-console.palona.ai/ | https://lat-api.palona.ai/ |
| stg | http://stg-manage-app.palona.ai/ | https://stg-console.palona.ai/ | https://stg-api.palona.ai/ |
| prd | http://manage-app.palona.ai/     | https://console.palona.ai/     | https://api.palona.ai/     |
