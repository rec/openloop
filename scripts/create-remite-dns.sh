#!/usr/bin/env bash
set -euo pipefail

cloudflare_account_id=44066e01f0c0660a57222615b9fc72e1

read -rsp 'Cloudflare API token: ' cf_api_token
echo

zone_id=$(
  curl -fsS \
    -H "Authorization: Bearer $cf_api_token" \
    "https://api.cloudflare.com/client/v4/zones?account.id=$cloudflare_account_id&name=ax.to&status=active" |
    jq -er '.result[0].id'
)
server_ip=$(dig +short A server.swirly.com | head -n 1)

if [[ -z $server_ip ]]; then
  echo 'server.swirly.com has no IPv4 address' >&2
  exit 1
fi

response=$(
  curl -fsS -X POST \
    "https://api.cloudflare.com/client/v4/zones/$zone_id/dns_records" \
    -H "Authorization: Bearer $cf_api_token" \
    -H 'Content-Type: application/json' \
    --data "$(
      jq -n \
        --arg name remite.ax.to \
        --arg content "$server_ip" \
        '{type: "A", name: $name, content: $content, ttl: 300, proxied: false}'
    )"
)

jq -e '.success' <<<"$response" >/dev/null
jq -r '"Created \(.result.name) -> \(.result.content)"' <<<"$response"
