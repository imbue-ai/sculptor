from enum import StrEnum
from pathlib import Path

CONTAINER_SSH_PORT = 22


class TmuxMode(StrEnum):
    APPEND = "append"
    IGNORE = "ignore"
    REPLACE = "replace"


class BashMode(StrEnum):
    APPEND = "append"
    IGNORE = "ignore"
    REPLACE = "replace"


TMUX_CONTENTS = """
set -g @resurrect-capture-pane-contents 'on'
set -g @resurrect-restore 'on'
set -g mouse on
run '~/.tmux/plugins/tmux-resurrect/resurrect.tmux'
"""

BASHRC_CONTENTS = r"""
# ~/.bashrc: executed by bash(1) for non-login shells.

# Note: PS1 and umask are already set in /etc/profile. You should not
# need this unless you want different defaults for root.
# PS1='${debian_chroot:+($debian_chroot)}\h:\w\$ '
# umask 022


# You may uncomment the following lines if you want `ls' to be colorized:
# export LS_OPTIONS='--color=auto'
# eval "$(dircolors)"
# alias ls='ls $LS_OPTIONS'
# alias ll='ls $LS_OPTIONS -l'
# alias l='ls $LS_OPTIONS -lA'
#
# Some more alias to avoid making mistakes:
# alias rm='rm -i'
# alias cp='cp -i'
# alias mv='mv -i'

mkdir -p "$HOME/.local/bin"
touch "$HOME/.local/bin/env"
. "$HOME/.local/bin/env"

function log_command() {
    # Get the last command's exit code immediately
    local exit_code=$?

    # Get the last command from history
    local cmd=$(history 1 | sed 's/^\s*[0-9]*\s*//')

    # Only log actual commands (not empty lines, etc)
    if [ -n "$cmd" ] && [ "$cmd" != "$PROMPT_COMMAND" ]; then
#        echo "$(date '+%Y-%m-%d %H:%M:%S') Command: $cmd (Exit: $exit_code)" >> ~/.command_history.log
        echo "$exit_code:$cmd" >> ~/.command_history.$SESSION.log
    fi
}

# Add our function to PROMPT_COMMAND (preserve any existing prompt command)
if [ -z "$PROMPT_COMMAND" ]; then
    PROMPT_COMMAND="log_command"
else
    PROMPT_COMMAND="log_command;$PROMPT_COMMAND"
fi

stty cbreak
"""

# the user cannot be hardcoded; this is temporary until we load the user based on the dockerfile
SCULPTOR_USER = "sculptoruser"
AGENT_DATA_PATH = Path("/agent/data")
ENVIRONMENT_WORKSPACE_DIRECTORY = Path("/code")
