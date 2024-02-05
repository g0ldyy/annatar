#!/bin/bash
set -ueo pipefail

kind=${1:-}
term=${2:-}
provider=${3:-premiumize}
max_results=2

if [ -z "${kind}" ] || [ -z "${term}" ]; then
	echo "Usage: $0 <kind> <term> [provider]"
	exit 1
fi

if [ "${provider}" == "real-debrid" ]; then
	debrid_api_key=$(op read "op://Personal/Real-debrid/API Token")
elif [ "${provider}" == "premiumize" ]; then
	debrid_api_key=$(op read "op://Personal/Premiumize.me/API Key")
else
	echo "Invalid provider: ${provider}"
	exit 1
fi

config=$(cat <<-EOF | jq -c . | base64 -w0
{
	"debrid_service": "${provider}",
	"debrid_api_key": "${debrid_api_key}",
	"max_results": ${max_results}
}
EOF
)

echo "${term}" \
	| tr ',' '\n' \
	| xargs -I{} -P8 \
		http --timeout 60 \
			GET \
			":8000/${config}/stream/${kind}/{}.json"
