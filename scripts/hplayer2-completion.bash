#!/bin/bash
# Bash completion for hplayer2

_hplayer2_completion() {
    local cur prev opts
    COMPREPLY=()
    cur="${COMP_WORDS[COMP_CWORD]}"
    prev="${COMP_WORDS[COMP_CWORD-1]}"

    # Get the directory where hplayer2 script is located
    local script_dir="$(cd "$(dirname "${COMP_WORDS[0]}")" && pwd)"
    local profiles_dir="$script_dir/profiles"

    # If profiles directory exists, list .py files without extension
    if [ -d "$profiles_dir" ]; then
        local profiles=$(cd "$profiles_dir" && ls -1 *.py 2>/dev/null | sed 's/\.py$//' | grep -v '^__')
        COMPREPLY=( $(compgen -W "$profiles" -- "$cur") )
    fi

    return 0
}

# Register the completion function
complete -F _hplayer2_completion hplayer2
complete -F _hplayer2_completion ./hplayer2
