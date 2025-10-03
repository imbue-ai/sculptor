#!/usr/bin/env bash
# Reset to the user's original PATH, plus just a few of our things.
export PATH=${_IMBUE_USER_ORIGINAL_PATH}:/imbue_addons/agent_path_extension_bin/
exec /imbue/nix_bin/bash "$@"
