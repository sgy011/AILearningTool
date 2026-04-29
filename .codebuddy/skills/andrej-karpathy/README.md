# Karpathy-Inspired Coding Guidelines (OpenClaw Skill)

Behavioral guidelines to reduce common LLM coding mistakes, derived from [Andrej Karpathy's observations](https://x.com/karpathy/status/2015883857489522876) on LLM coding pitfalls.

Adapted from [forrestchang/andrej-karpathy-skills](https://github.com/forrestchang/andrej-karpathy-skills) for **OpenClaw**.

## The Four Principles

| Principle | Addresses |
|-----------|-----------|
| **Think Before Coding** | Wrong assumptions, hidden confusion, missing tradeoffs |
| **Simplicity First** | Overcomplication, bloated abstractions |
| **Surgical Changes** | Orthogonal edits, touching code you shouldn't |
| **Goal-Driven Execution** | Tests-first approach, verifiable success criteria |

## Install

### SkillHub (recommended)

```bash
skillhub install karpathy-guidelines
```

### Manual

Copy the entire `karpathy-guidelines` folder to your OpenClaw skills directory:

```bash
cp -r karpathy-guidelines ~/.qclaw/skills/
```

## Structure

```
karpathy-guidelines/
├── SKILL.md                    # Core guidelines (4 principles)
├── references/
│   └── examples.md             # Detailed code examples
└── README.md                   # This file
```

## Key Insight

> "LLMs are exceptionally good at looping until they meet specific goals... Don't tell it what to do, give it success criteria and watch it go."

The "Goal-Driven Execution" principle captures this: transform imperative instructions into declarative goals with verification loops.

## How to Know It's Working

- **Fewer unnecessary changes in diffs** — Only requested changes appear
- **Fewer rewrites due to overcomplication** — Code is simple the first time
- **Clarifying questions come before implementation** — Not after mistakes
- **Clean, minimal PRs** — No drive-by refactoring or "improvements"

## License

MIT
