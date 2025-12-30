# ask

`ask` is a terminal-first assistant that turns plain-English requests into macOS zsh commands. It uses LM Studio as the local LLM backend, so you can describe what you want and review the suggested command (or direct answer) before running anything on your machine.

`ask` exists to bridge the gap between natural language and the terminal, without auto-running commands or shipping data to the cloud.

## Installation

Prerequisites:

- Python 3.10+
- LM Studio running locally (see below)

```bash
git clone https://github.com/morgang5522/ask.git
cd ask
python -m venv .venv && source .venv/bin/activate
pip install .
```

This installs an `ask` console script.

### Install globally (use anywhere)

If you prefer to make `ask` available in every shell without activating a virtualenv, install it with either `pipx` or `pip --user`:

```bash
# pipx keeps the tool isolated but exposes `ask` on your PATH
pipx install git+https://github.com/morgang5522/ask.git

# or, from a local clone:
pipx install .
```

Without pipx:

```bash
pip install --user git+https://github.com/morgang5522/ask.git
```

After installation, ensure `~/.local/bin` (or the path pipx reports) is on your `PATH` so you can call `ask` from any terminal tab.

## LM Studio setup

1. Launch LM Studio and start an API server (menu: Run → OpenAI-Compatible Server).
2. Select a chat model (the defaults expect `qwen/qwen3-vl-8b`, but you can choose any compatible model).
3. Note the host/port of the server. By default, Ask points to `http://localhost:1234` with endpoint `/v1/chat/completions`.

You can override the connection details via either CLI flags or environment variables:

- `LMSTUDIO_BASE_URL` (default `http://localhost:1234`)
- `LMSTUDIO_ENDPOINT` (default `/v1/chat/completions`)
- `LMSTUDIO_MODEL` (default `qwen/qwen3-vl-8b`)

Example:

```bash
export LMSTUDIO_BASE_URL="http://localhost:8080"
export LMSTUDIO_MODEL="qwen/qwen2.5-7b"
ask "list the Git branches"
```

## Usage

Basic invocation:

```bash
ask "find the five largest files here"
```

Key options:

- `--run`: Automatically run the suggested command after confirmation.
- `--yes`: Run without prompting (dangerous—use only in trusted scenarios).
- `--session`: Persist conversation history across invocations.
- `--temperature`: Adjust creativity of the model response.
- `--base-url`, `--endpoint`, `--model`: Override LM Studio connection details per run.

If you omit the query, Ask drops you into an interactive prompt with history and TAB-completion for follow-up questions.

## Safety and AI warnings

- This tool is AI powered. The model may misunderstand requests or suggest incorrect/dangerous commands. Always read and understand the output before you run it.
- Ask never auto-executes unless you pass `--run` (and even then it asks for confirmation unless `--yes` is provided). Keep that safety net in place when trying unfamiliar commands.
- Treat natural-language answers as advice, not guaranteed truth. Verify important instructions independently, especially when they involve system changes or sensitive data.

By using `ask` you acknowledge that you remain responsible for the commands you execute on your machine.

## Tests

```bash
pip install pytest
pytest
```

## Licence

Licensed under the MIT License. See [LICENSE](LICENSE.md) for details.

## TODO

- Add instructions for LM Studio starting when macOS starts
- Add better configuration for permanent changes to models/URLs without needing env vars
- Tweak model prompt to make it a bit more useful
- Maybe add to `homebrew`?
