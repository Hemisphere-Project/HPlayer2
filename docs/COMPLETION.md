# HPlayer2 Shell Completion

Tab completion for hplayer2 profile names.

## Automatic Installation

Completion is automatically installed when you run:
```bash
./scripts/install_macos.sh    # macOS
./scripts/install_xbian.sh    # Linux/xbian
```

## Manual Setup

For **zsh**:
```bash
# Add to ~/.zshrc
echo 'fpath=(/path/to/HPlayer2/scripts $fpath)' >> ~/.zshrc
echo 'autoload -Uz compinit && compinit' >> ~/.zshrc
source ~/.zshrc
```

For **zsh** (current session only):
```bash
fpath=(/path/to/HPlayer2/scripts $fpath)
autoload -Uz compinit && compinit
```

For **bash** (current session):
```bash
source /path/to/HPlayer2/scripts/hplayer2-completion.bash
```

## Usage

After setup, you can use tab completion:
```bash
./hplayer2 25-ann<TAB>     # Completes to 25-annatv
./hplayer2 d<TAB>          # Shows: default, decaz
./hplayer2 bie<TAB>        # Shows: biennale24, biennale24-midi, biennale24-rtc
```

## Files

- `scripts/hplayer2-completion.bash` - Bash completion script
- `scripts/_hplayer2` - Zsh completion script
