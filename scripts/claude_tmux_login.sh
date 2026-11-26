# claude_tmux_login.sh — sourced at SSH login (/etc/profile.d/zz-claude-tmux.sh, laid by
# ssh_pakker.sh at every add-on start). cclaude runs Claude Code in a tmux session named
# claude-<ddHHMMSS>, so it keeps working on the NUC when the phone drops between wifi and
# mobile (user 2026-11-26). Here a new login hangs on to the session left behind:
#   a detached claude-* session → attach to the newest one;
#   only attached ones (sshd notices a dead phone after up to 30 min: ClientAliveInterval
#   600 × 3, so the lost connection still "holds" it) → say so; `cca` takes it over.
if [ -z "${TMUX:-}" ] && [ -t 0 ] && [ -t 1 ] && command -v tmux >/dev/null 2>&1; then
  _cs=$(command tmux ls -F '#{session_attached} #{session_activity} #{session_name}' 2>/dev/null | awk '$3 ~ /^claude-/' | sort -k2,2nr)
  _det=$(printf '%s\n' "$_cs" | awk '$1 == 0 { print $3; exit }')
  if [ -n "$_det" ]; then
    command tmux attach -t "$_det"
  elif [ -n "$_cs" ]; then
    printf 'Claude kører i tmux (%s) — skriv cca for at hænge på.\n' "$(printf '%s\n' "$_cs" | awk '{ print $3 }' | tr '\n' ' ' | sed 's/ $//')"
  fi
  unset _cs _det
fi
