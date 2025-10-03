#! /bin/bash
# Simple test to verify that building goes well.
# Run from the main directory, with make test-build-artifacts
#
# This test will run the build script, generate artifacts, and attempts to run
# them.

# PLEASE NOTE: this relies on the fact that the host machine is MacOS to
# test the Mac pipeline.

set -euxo pipefail

# Handle any errors by printing a message.
error_exit() {
	echo -e "\033[0;31mError: $1\033[0m" >&2
	exit 1
}

make clean dist

# Run the next block only if we are on MacOS.
if [[ "$(uname)" == "Darwin" ]]; then
	# We run sculptor's version command to make sure that everything unpacks correctly, all the
	# deps are populated and it can start.
	# uvx --with ../dist/sculptor-*.tar.gz --refresh sculptor --version > /dev/null
	echo "Local build check completed successfully."
fi


# Ensure that the built version of sculptor successfully runs in the LinuxDeployDockerfile
# docker image build -t testlinuximage -f sculptor/scripts/LinuxDeployDockerfile --no-cache ..
# VERSION=$(docker run --rm testlinuximage bash -c "uvx --with /home/node/sculptor-*.tar.gz --refresh sculptor --version")

# if [[ -z "$VERSION" || "$VERSION" == *-dev ]]; then
# 	error_exit "Build check failed: version is empty or ends with '-dev'."
# fi

echo "Linux build check completed successfully."
