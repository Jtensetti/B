#!/bin/sh
set -eu
here=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
repo=$(git -C "$here" rev-parse --show-toplevel)
frozen=01a91593241803567c35534acbe3e041d4936b11
ctx=$(mktemp -d)
trap 'rm -rf "$ctx"' EXIT
mkdir "$ctx/code"
git -C "$repo" archive -o "$ctx/code.tar" "$frozen" b_lang b_examples dotnet pyproject.toml README.md
tar xf "$ctx/code.tar" -C "$ctx/code"
rm "$ctx/code.tar"
cp "$here"/Dockerfile "$here"/package*.json "$ctx/"
docker build --label "org.opencontainers.image.revision=$frozen" -t b-sibling-c:0.32 "$ctx"
