# pal-mono

TODO

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
