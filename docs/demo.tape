# MudaleTunnel CLI demo — rendered with charmbracelet/vhs.
#
#   ./docs/demo-setup.sh && vhs docs/demo.tape
#
# The commands are real: they hit the live API, through the same authentication,
# scope checks and audit trail as any other client. The *data* is invented —
# `manage.py seed_sample_data` writes a fictional engagement so a published
# recording contains no real network. The scope refusals near the end are
# genuinely evaluated live.

Output docs/demo.gif

Set Shell "bash"
Set FontSize 15
Set Width 1160
Set Height 700
Set Padding 24
Set Theme { "name": "mudale", "background": "#09090b", "foreground": "#fafafa", "cursor": "#22d3ee", "selection": "#27272a", "black": "#18181b", "red": "#ef4444", "green": "#22c55e", "yellow": "#f59e0b", "blue": "#3b82f6", "magenta": "#a78bfa", "cyan": "#22d3ee", "white": "#a1a1aa", "brightBlack": "#52525b", "brightRed": "#ef4444", "brightGreen": "#22c55e", "brightYellow": "#f59e0b", "brightBlue": "#3b82f6", "brightMagenta": "#a78bfa", "brightCyan": "#67e8f9", "brightWhite": "#fafafa" }
Set TypingSpeed 30ms

Hide
Type "source /tmp/mudale-demo/env.sh && clear" Enter
Sleep 1s
Show

Type "mudale status"  Sleep 300ms  Enter
Sleep 2.8s

Type "mudale engagements"  Sleep 300ms  Enter
Sleep 3.2s

Type "clear"  Enter  Sleep 400ms

# ── Scope is enforced in code, and evaluated live ───────────────────────
Type "# Every target is checked against the engagement's authorised ranges."  Enter
Sleep 1.1s
Type "mudale scan run --engagement 10 --target 8.8.8.8 --profile quick"  Sleep 300ms  Enter
Sleep 2.8s
Type "# A /16 allowance does not permit the enclosing /8."  Enter
Sleep 1.1s
Type "mudale scan run --engagement 10 --target 10.0.0.0/8 --profile quick"  Sleep 300ms  Enter
Sleep 2.8s
Type "# And an argv-injection attempt is not a target at all."  Enter
Sleep 1.1s
Type "mudale scan run --engagement 10 --target '-oN /tmp/pwned' --profile quick"  Sleep 300ms  Enter
Sleep 3s

Type "clear"  Enter  Sleep 400ms

# ── The pivot and what it opened ────────────────────────────────────────
Type "# A SOCKS proxy through the foothold, and a forward built from a finding."  Enter
Sleep 1.1s
Type "mudale tunnels"  Sleep 300ms  Enter
Sleep 4s

Type "clear"  Enter  Sleep 400ms

Type "# Reachability, grouped by the pivot that proved it."  Enter
Sleep 1.1s
Type "mudale pivot map --engagement 10"  Sleep 300ms  Enter
Sleep 5.5s

Type "clear"  Enter  Sleep 400ms

# ── What the scan found ─────────────────────────────────────────────────
Type "# Services discovered by scanning THROUGH the pivot."  Enter
Sleep 1.1s
Type "mudale scan services 11"  Sleep 300ms  Enter
Sleep 5s

Type "clear"  Enter  Sleep 400ms

# ── proxychains ─────────────────────────────────────────────────────────
Type "# Tools that speak SOCKS get a ready-made config."  Enter
Sleep 1.1s
Type "mudale pivot proxychains 13"  Sleep 300ms  Enter
Sleep 5s

Type "clear"  Enter  Sleep 400ms

# ── The trail ───────────────────────────────────────────────────────────
Type "# Every action, and every refusal, with the operator who caused it."  Enter
Sleep 1.1s
Type "mudale audit --limit 6"  Sleep 300ms  Enter
Sleep 6s
