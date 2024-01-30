#!/bin/bash
set -ueo pipefail

kind=${1:-}
term=${2:-}

if [ -z "${kind}" ] || [ -z "${term}" ]; then
	echo "Usage: $0 <kind> <term>"
	exit 1
fi

# http --timeout 30 \
# 	":8000/stream/${kind}/${term}.json" \
# 	streamService==real-debrid \
# 	jackettUrl==https://jackett.blockloop.io \
# 	jackettApiKey==$(op read "op://Personal/Jackett/API KEY") \
# 	debridApiKey==$(op read "op://Personal/Real-debrid/API Token") \
# 	maxResults==5

http --timeout 30 \
	":8000/stream/${kind}/${term}.json" \
	streamService==premiumize \
	jackettUrl==https://jackett.blockloop.io \
	jackettApiKey==$(op read "op://Personal/Jackett/API KEY") \
	debridApiKey==$(op read "op://Personal/Premiumize/API Key") \
	maxResults==5
