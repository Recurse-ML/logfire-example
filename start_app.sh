#!/bin/env bash

# TODO: verify that there are no unpushed changes
#
export GIT_COMMIT=$(git rev-parse HEAD)
export GIT_REPO_URL=$(git config --get remote.origin.url)
docker compose watch
