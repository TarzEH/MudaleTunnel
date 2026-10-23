# Contributing to MudaleTunnel

Thanks for your interest in contributing! Here's how to get started.

## Quick setup

```bash
git clone https://github.com/TarzEH/MudaleTunnel.git
cd MudaleTunnel
cp .env.example .env
make dev        # starts Postgres + Redis
cd backend && uv venv && uv pip install -e ".[server,dev]"
cd ../frontend && npm install
```

Run the tests before submitting:

```bash
make test
make lint
```

## What to work on

Check the [open issues](https://github.com/TarzEH/MudaleTunnel/issues), especially ones labelled **good first issue**. If you want to work on something, comment on the issue so others know.

## Pull requests

1. Fork the repo and create a branch from `master`.
2. Keep changes focused — one feature or fix per PR.
3. Add tests for new functionality.
4. Make sure `make test` and `make lint` pass.
5. Write a clear PR description explaining **what** and **why**.

## Code style

- Python: formatted and linted by [Ruff](https://docs.astral.sh/ruff/) (`ruff check .`).
- TypeScript: type-checked with `tsc --noEmit`.
- No unused imports, no `print()` left behind.

## Reporting bugs

Open an issue using the **Bug report** template. Include:
- Steps to reproduce
- Expected vs actual behaviour
- Python version and OS

## Feature requests

Open an issue using the **Feature request** template. Describe the use case before the solution.

## License

By contributing you agree that your contributions are licensed under the [MIT License](LICENSE).
