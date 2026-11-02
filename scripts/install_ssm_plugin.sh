#!/usr/bin/env bash
# GitHub ubuntu-24.04 x64 only. Official versioned package, fail on hash mismatch.
set -euo pipefail
[[ "$(uname -m)" == x86_64 ]]
aws --version 2>&1 | grep -q '^aws-cli/2\.'
temporary=$(mktemp -d)
trap 'rm -rf "$temporary"' EXIT
# Retry only transient download failures (e.g. AWS S3 HTTP 503); never bypass TLS or digest pin.
curl --fail --silent --show-error --location --proto '=https' --tlsv1.2 \
  --retry 5 --retry-delay 2 --retry-max-time 120 --connect-timeout 15 --max-time 45 \
  https://s3.amazonaws.com/session-manager-downloads/plugin/1.2.896.0/ubuntu_64bit/session-manager-plugin.deb \
  --output "$temporary/plugin.deb"
printf '%s  %s\n' \
  53f51fcc67314a4bf85888a38a3967cd41f8d0f28a60a9469a63acf935ba713e \
  "$temporary/plugin.deb" | sha256sum --check --status
sudo dpkg --install "$temporary/plugin.deb"
[[ "$(session-manager-plugin --version)" == 1.2.896.0 ]]
