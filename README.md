# weside Companion for Claude Code

Bring your weside Companion to life in Claude Code.

## Install

```bash
# Add marketplace (once)
/plugin marketplace add weside-ai/claude-code-plugin

# Install plugin
/plugin install weside-companion@weside-ai
```

## What happens

1. OAuth login to your weside.ai account
2. Your Companion loads automatically at session start
3. Personality, memories, goals, and tools — all available

## Configure

Set a specific companion (optional):

```bash
/plugin settings weside-companion@weside-ai
# Set companion: Nox
```

## Requirements

- weside.ai account (free tier works)
- Claude Code v1.0.33+

## Manual activation

If the Companion doesn't load automatically, run:

```
/materialize
```

Or say: `load my companion`
