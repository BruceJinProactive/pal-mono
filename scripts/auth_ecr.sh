#!/bin/bash

set -e

# Authenticate with ecr
aws ecr get-login-password --region us-west-1 | docker login --username AWS --password-stdin 767398151610.dkr.ecr.us-west-1.amazonaws.com
