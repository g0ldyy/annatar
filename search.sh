#!/bin/bash
set -ueo pipefail

kind=${1:-}
term=${2:-}
provider=${3:-premiumize}
max_results=5

if [ -z "${kind}" ] || [ -z "${term}" ]; then
	echo "Usage: $0 <kind> <term> [provider]"
	exit 1
fi

if [ "${provider}" == "real-debrid" ]; then
	http --timeout 60 \
		":8000/stream/${kind}/${term}.json" \
		streamService==real-debrid \
		debridApiKey==$(op read "op://Personal/Real-debrid/API Token") \
		maxResults==${max_results}
elif [ "${provider}" == "premiumize" ]; then
	http --timeout 60 \
		":8000/stream/${kind}/${term}.json" \
		streamService==premiumize \
		debridApiKey==$(op read "op://Personal/Premiumize/API Key") \
		maxResults==${max_results}
else
	echo "Invalid provider: ${provider}"
	exit 1
fi
