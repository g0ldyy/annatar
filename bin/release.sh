#!/bin/bash

main() {
	release

	while true; do
		read -p "Do you wish to continue? (yes/no) " yn
		case $yn in
			[Yy]* ) set -x; glab release create -r master "${VERSION}" --notes "${RELEASE_NOTES}"; set +x; break;;
			[Nn]* ) echo "Cancelled"; exit;;
			* ) echo "Please answer yes or no.";;
		esac
	done
}


release() {
	VERSION=$(git describe --tags --abbrev=0 | awk -F. '{$NF+=1; OFS="."; $1=$1; print $0}')
	RELEASE_NOTES=$(git log --graph --format='%h - %s' --abbrev-commit $(git describe --tags --abbrev=0)..HEAD)
	cat <<-EOF
	Version: ${VERSION}
	Release Notes:

	${RELEASE_NOTES}

	EOF
}

main
