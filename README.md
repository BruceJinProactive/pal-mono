# pal-mono

TODO

## Setup

### Pre-req

Make sure Python3 and Pip3 are installed on your Mac

### Install dependencies

Create a virtual environment in the terminal and install dependencies

```jsx
python3 -m venv ~/.venvs/aienv
source ~/.venvs/aienv/bin/activate

pip install -U phidata
phi init
phi ws setup
```

### Setup OpenAI API key in your environment variable

```jsx
export OPENAI_API_KEY=sk-***
```

## Run both API and web app locally to test and debug

```jsx
phi ws up
```

## Dev

### Build and push the image

```jsx
phi ws up --env dev --infra docker --type image
```

### Restart all containers

```jsx
phi ws restart --env dev --infra docker --type container
```

## Prd

### Build and push the image

```jsx
phi ws up --env prd --infra docker --type image
```

### Update ECS Service to redeploy

```jsx
phi ws patch --env prd --infra aws --name service
```
