import argparse
import json
import os
import subprocess
from dataclasses import dataclass
from typing import Any, Dict, List

import requests
from platformdirs import user_config_dir
from prompt_toolkit import PromptSession
from prompt_toolkit.completion import PathCompleter
from prompt_toolkit.history import FileHistory
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

console = Console()

DEFAULT_BASE_URL = os.environ.get("LMSTUDIO_BASE_URL", "http://localhost:1234")
DEFAULT_ENDPOINT = os.environ.get("LMSTUDIO_ENDPOINT", "/v1/chat/completions")
DEFAULT_MODEL = os.environ.get("LMSTUDIO_MODEL", "qwen/qwen3-vl-8b")

SYSTEM_PROMPT = """You are a helpful assistant that can either:
(A) answer normally in text, OR
(B) produce a macOS zsh command the user can run.

DEFAULT BEHAVIOR:
- Prefer type="answer" unless running a shell command is clearly the best way to achieve the user's goal.
- Only return type="command" when the user is asking to do something with their computer, filesystem, installed tools, networking, or automation.

WHEN TO USE type="command" (strong signals):
- The user asks to convert, resize, download, move, rename, search files, inspect disk/CPU/network, run git/docker/kubectl, install packages, manipulate archives, process logs, automate a repeated task, or run a script.
- The request mentions files/folders/paths/extensions, or "in this folder", "on my Mac", "in Terminal", "command", "script", "zsh", "brew", "ffmpeg", etc.

WHEN NOT TO USE type="command" (strong signals):
- General knowledge, explanations, opinions, recommendations, definitions, reasoning, planning, writing, summaries.
- Questions about concepts (e.g., “how does X work?”) where a command would not materially help.
- “How do I…?” questions that are not specifically about operating this Mac (e.g., baking, relationships, history).
- If the user asks for help choosing between options, deciding, or understanding—use type="answer".

CRITICAL RULE:
- Do NOT invent shell commands just to look helpful.
- If a command would only print information that you can directly explain, use type="answer" instead.
- If the user could solve the request by reading your explanation without running anything, use type="answer".

SAFETY:
- Prefer safe commands. Avoid destructive actions.
- Never propose `rm -rf`, `sudo`, disk formatting, system modifications, credential scraping, or anything risky unless the user explicitly requests it AND you ask a follow-up confirmation question.
- You will not answer NSFW questions.

FOLLOW-UPS:
- Ask a follow-up question (type="question") when you cannot complete the request without missing essential info, or when you need to provide additional guidance after the command runs.
- If the user has asked you to explain or interpret the output of a command, set "follow_up": true.
- Verbs such as tell, explain, interpret, analyze, summarize, etc. indicate a follow-up is needed.

OUTPUT FORMAT:
Return JSON only, with exactly this schema:
{
  "type": "question" | "command" | "answer",
  "message": "<string>",
  "command": "<string or empty>",
  "follow_up": "<true or false>"
}

RESPONSE RULES:
- If more info is needed, use type="question" and put only the question in message. Set "follow_up": true.
- Use type="command" only when the user genuinely needs a shell command. Put the command in "command" and a short explanation (1–3 sentences) in "message". Set "follow_up": true only when you expect to comment on the command results afterward; otherwise false.
- If the user only needs an explanation and no shell command, use type="answer" and leave "command" empty. Set "follow_up": true only when further conversation is needed; otherwise false.
- Never wrap JSON in markdown fences. Return JSON only.

CALIBRATION EXAMPLES (follow these patterns exactly):
User: "how do I bake a cake?"
Assistant: {"type":"answer","message":"Explain the basic steps and temperatures briefly...","command":""}

User: "convert this file from webm to mp4"
Assistant: {"type":"question","message":"What is the filename/path of the .webm file, and what output name do you want for the .mp4?","command":""}

User: "what does chmod do?"
Assistant: {"type":"answer","message":"Explain chmod conceptually with one short example...","command":""}

User: "find large files in this folder"
Assistant: {"type":"command","message":"This lists the largest files in the current directory.","command":"du -sh * | sort -h"}

User: "is it normal to feel anxious before presentations?"
Assistant: {"type":"answer","message":"Give reassurance and practical tips...","command":""}
"""

@dataclass
class LLMConfig:
    base_url: str
    endpoint: str
    model: str
    temperature: float = 0.0
    timeout_s: int = 60

def config_dir() -> str:
    d = user_config_dir("ask-cli")
    os.makedirs(d, exist_ok=True)
    return d

def history_path() -> str:
    return os.path.join(config_dir(), "history.txt")

def session_path() -> str:
    return os.path.join(config_dir(), "session.json")

def load_session() -> List[Dict[str, str]]:
    try:
        with open(session_path(), "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
    except FileNotFoundError:
        pass
    except Exception:
        # If session corrupt, just start fresh
        pass
    return []

def save_session(messages: List[Dict[str, str]]) -> None:
    with open(session_path(), "w", encoding="utf-8") as f:
        json.dump(messages, f, ensure_ascii=False, indent=2)

def clear_session() -> None:
    try:
        os.remove(session_path())
    except FileNotFoundError:
        pass

def call_llm(cfg: LLMConfig, messages: List[Dict[str, str]]) -> Dict[str, Any]:
    url = cfg.base_url.rstrip("/") + cfg.endpoint
    payload = {
        "model": cfg.model,
        "messages": messages,
        "temperature": cfg.temperature,
    }
    r = requests.post(url, json=payload, timeout=cfg.timeout_s)
    r.raise_for_status()
    data = r.json()
    content = data["choices"][0]["message"]["content"]
    try:
        parsed = json.loads(content)
        if not isinstance(parsed, dict):
            raise ValueError("LLM did not return a JSON object")
        parsed.setdefault("follow_up", False)
        return parsed
    except Exception as e:
        # Fall back: show raw content for debugging
        return {
            "type": "question",
            "message": f"LLM returned non-JSON. Raw:\n{content}\n\nError: {e}",
            "command": "",
            "follow_up": False,
        }

def pretty_command(cmd: str) -> Panel:
    t = Text(cmd)
    return Panel(t, title="Command", border_style="green")

def pretty_message(msg: str) -> Panel:
    return Panel(Text(msg), title="Assistant", border_style="cyan")

def pretty_user(msg: str) -> Panel:
    return Panel(Text(msg), title="You", border_style="magenta")

def run_shell_command(cmd: str) -> subprocess.CompletedProcess:
    # Run using user's shell for normal zsh compatibility, but safely.
    # We avoid shell=True; instead invoke /bin/zsh -lc "<cmd>"
    return subprocess.run(
        ["/bin/zsh", "-lc", cmd],
        text=True,
        capture_output=True,
    )

def interactive_followups(session: PromptSession, prompt_text: str) -> str:
    # PathCompleter enables TAB completion for files/folders
    path_completer = PathCompleter(expanduser=True)
    return session.prompt(prompt_text, completer=path_completer)

def main():
    parser = argparse.ArgumentParser(prog="ask", description="Plain-English to shell commands via LM Studio")
    parser.add_argument("query", nargs="*", help="Your plain-English request (if omitted, you’ll be prompted)")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="LM Studio base URL (default: http://localhost:1234)")
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT, help="Chat completions endpoint (default: /v1/chat/completions)")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Model name (LM Studio ignores sometimes; kept for compatibility)")
    parser.add_argument("--temperature", type=float, default=0.0, help="LLM temperature")
    parser.add_argument("--run", action="store_true", help="Run the generated command after confirmation")
    parser.add_argument("--yes", action="store_true", help="Skip confirmation (dangerous)")
    parser.set_defaults(session=False)
    parser.add_argument("--session", dest="session", action="store_true", help="Persist conversation session across invocations")
    parser.add_argument("--no-session", dest="session", action="store_false", help="Disable session persistence (default)")
    parser.add_argument("--reset", action="store_true", help="Reset the saved conversation session")
    args = parser.parse_args()

    cfg = LLMConfig(
        base_url=args.base_url,
        endpoint=args.endpoint,
        model=args.model,
        temperature=args.temperature,
    )

    if args.reset:
        clear_session()
        console.print("[green]Session cleared.[/green]")
        return

    # Prompt session with persisted history (shell-like up-arrow)
    session = PromptSession(history=FileHistory(history_path()))

    # Starting user query
    query = " ".join(args.query).strip()
    if not query:
        query = interactive_followups(session, "Ask (plain English): ").strip()

    if not query:
        console.print("[yellow]No request provided.[/yellow]")
        return

    console.print(pretty_user(query))

    # Load or start messages
    messages: List[Dict[str, str]] = []
    if args.session:
        messages = load_session()

    # Ensure system prompt exists at start
    if not messages or messages[0].get("role") != "system":
        messages = [{"role": "system", "content": SYSTEM_PROMPT}] + [m for m in messages if m.get("role") != "system"]

    # Add context about cwd (helpful for “this file”)
    cwd = os.getcwd()
    messages.append({"role": "user", "content": f"My current directory is: {cwd}\nRequest: {query}"})

    # Loop: LLM may ask follow-ups
    while True:
        with console.status("[bold green]Asking the AI...[/bold green]"):
            result = call_llm(cfg, messages)
        rtype = (result.get("type") or "").strip().lower()
        msg = (result.get("message") or "").strip()
        cmd = (result.get("command") or "").strip()
        follow_up = bool(result.get("follow_up"))

        if msg:
            console.print(pretty_message(msg))

        if rtype == "question":
            messages.append({"role": "assistant", "content": json.dumps(result)})
            answer = interactive_followups(session, "Answer: ").strip()

            if not answer:
                console.print("[yellow]No answer provided. Exiting.[/yellow]")
                break
            console.print(pretty_user(answer))
            messages.append({"role": "user", "content": answer})
            continue

        if rtype == "answer":
            messages.append({"role": "assistant", "content": json.dumps(result)})
            if follow_up:
                continue
            break

        if rtype == "command":
            if not cmd:
                console.print("[red]LLM returned type=command but no command.[/red]")
                break

            console.print(pretty_command(cmd))

            # Confirmation before running
            if args.yes:
                do_run = True
            elif args.run:
                yn = session.prompt("Run this? [y/N]: ").strip().lower()
                do_run = yn in ("y", "yes")
            else:
                do_run = False

            if do_run:
                console.print("[bold]Running…[/bold]")
                completed = run_shell_command(cmd)
                console.print(f"[bold]Exit code:[/bold] {completed.returncode}")
                if completed.stdout:
                    console.print(Panel(Text(completed.stdout.rstrip()), title="stdout", border_style="green"))
                if completed.stderr:
                    console.print(Panel(Text(completed.stderr.rstrip()), title="stderr", border_style="red"))
                # Tell the model what happened for next time
                messages.append({"role": "assistant", "content": json.dumps(result)})
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            f"The command returned exit code {completed.returncode}.\n"
                            f"STDOUT:\n{completed.stdout}\nSTDERR:\n{completed.stderr}"
                        ),
                    }
                )
                if follow_up:
                    continue
                break

            # Still record assistant output for continuity
            messages.append({"role": "assistant", "content": json.dumps(result)})
            if follow_up:
                continue
            break

        # Unknown response type
        console.print("[red]LLM returned unknown type. Exiting.[/red]")
        break

    if args.session:
        save_session(messages)

if __name__ == "__main__":
    main()
