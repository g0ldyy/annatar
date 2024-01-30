#!/bin/bash
set -ueo pipefail

kind=${1:-}
term=${2:-}
provider=${3:-premiumize}

if [ -z "${kind}" ] || [ -z "${term}" ]; then
	echo "Usage: $0 <kind> <term> [provider]"
	exit 1
fi

if [ "${provider}" == "real-debrid" ]; then
	http --timeout 30 \
		":8000/stream/${kind}/${term}.json" \
		streamService==real-debrid \
		jackettUrl==https://jackett.blockloop.io \
		jackettApiKey==$(op read "op://Personal/Jackett/API KEY") \
		debridApiKey==$(op read "op://Personal/Real-debrid/API Token") \
		maxResults==5
elif [ "${provider}" == "premiumize" ]; then
	http --timeout 30 \
		":8000/stream/${kind}/${term}.json" \
		streamService==premiumize \
		jackettUrl==https://jackett.blockloop.io \
		jackettApiKey==$(op read "op://Personal/Jackett/API KEY") \
		debridApiKey==$(op read "op://Personal/Premiumize/API Key") \
		maxResults==5
else
	echo "Invalid provider: ${provider}"
	exit 1
fi
