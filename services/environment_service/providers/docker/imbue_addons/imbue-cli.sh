#!/imbue/nix_bin/bash
# This script sets the right environment for the imbue CLI to work, including LD_LIBRARY_PATH, to make numpy go.
source /imbue/env/env_for_imbue_cli.sh
# Make sure that imbue-cli has access to our git via PATH.
# But does imbue-cli want to run tools from the user's environment?  If so, there's now a weird mix of toolchain.
export PATH=/imbue/nix_bin:$PATH
/imbue/.venv/bin/imbue-cli "$@"
