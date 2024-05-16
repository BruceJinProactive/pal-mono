# pal-mono

## Development

Follow the next steps to run the pal-mono service on your local computer.

1. Pre-req: make sure Python3, Pip3 and Docker are installed on your Mac.

2. Checkout the repo and navigate to the root folder.
3. Create a python virtual environment

```bash
python3 -m venv ~/.venvs/aienv
source ~/.venvs/aienv/bin/activate
```

4. [One-time] Install dependencies

```bash
pip3 install -U phi
phi init
phi ws setup
```

5. Setup OpenAI API key in your environment variable

```bash
export OPENAI_API_KEY=sk-***
export LEPTON_API_KEY=***
```

6. Build and run both API and web app locally

```bash
phi ws up
```

## CI/CD

### Environments

The CI/CD pipeline is devided into 3 stages:

- dev(development) - The enviroment for your local development. Changes before merged into `main` branch.
- stg(staging) - The enviroment for internal testing and validation. Changes on the HEAD of `main` branch, before merged into `prd` branch.
- prd(production) - The enviroment to live customer traffic. Changes on `prd` branch.

### Releasing from `dev` to `stg`:

1. Create a feature branch `example-feature` based from `main` and make changes locally.
2. Make a pull request merging `example-feature` to `main`.
3. Wait for PR review and approval.
4. Submit the PR to merge `example-feature` to `main`.
5. A staging release will be automatically triggered. Join Slack channel #cicd-notifications to receive notificaionts.

### Releasing from `stg` to `prd`:

[TODO] The process is manual for now.

1. Make a pull request merging `prd` to `main`.
2. Wait for PR review and approval.
3. Submit the PR to merge `prd` to `main`.
4. A release release will be automatically triggered. Join Slack channel #cicd-notifications to receive notificaionts.

## Serving Endpoints

|     | app                                                                | api (Load Balancer)                                                | api (API Gateway)                                          |
| --- | ------------------------------------------------------------------ | ------------------------------------------------------------------ | ---------------------------------------------------------- |
| stg | http://pal-mono-stg-app-lb-1654020856.us-west-1.elb.amazonaws.com/ | http://pal-mono-stg-api-lb-1164693723.us-west-1.elb.amazonaws.com/ | https://5xtuyf38b8.execute-api.us-west-1.amazonaws.com/stg-api                                                          |
| prd | http://pal-mono-prd-app-lb-270235957.us-west-1.elb.amazonaws.com/  | http://pal-mono-prd-api-lb-222574634.us-west-1.elb.amazonaws.com/  | https://5xtuyf38b8.execute-api.us-west-1.amazonaws.com/api |
