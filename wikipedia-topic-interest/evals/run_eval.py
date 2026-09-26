#!/usr/bin/env python3
"""
Run the skill end to end through a real model over OpenRouter.

This exists because the requirement is that the skill be usable by a small, cheap,
fast model. The only way to know that is to give such a model SKILL.md, a shell
tool, and a question, and watch what it actually does.

    export OPENROUTER_API_KEY=sk-or-...
    python3 evals/run_eval.py --model anthropic/claude-haiku-4.5
    python3 evals/run_eval.py --model anthropic/claude-haiku-4.5 --case localisation -v

What is graded, per case:
  * did it call the CLI at all, and correctly (right flags, one call, no hand-rolled
    HTTP or ad-hoc statistics)
  * did the run succeed
  * does the written answer contain the things that make it trustworthy -
    the share-vs-raw distinction, confidence, and the demand caveat
  * did it avoid the specific failure modes this skill is built to prevent

Exit code is 0 only if every case passes.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

SKILL_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
API_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "anthropic/claude-haiku-4.5"
MAX_TURNS = 8
COMMAND_TIMEOUT = 180

SYSTEM_PROMPT = """You are a product analyst helping a B2C founder. You have one tool: `shell`.

A skill is installed at {root}. Its instructions are below. Follow them.
Use the skill's scripts rather than writing your own analysis code or HTTP calls.
Use `{python}` as the Python interpreter.

When you have the data, reply with your final answer in prose for the founder.

--- SKILL.md ---
{skill}
--- end SKILL.md ---"""

TOOLS = [{
    "type": "function",
    "function": {
        "name": "shell",
        "description": "Run a shell command in the skill directory and return stdout/stderr.",
        "parameters": {
            "type": "object",
            "properties": {"command": {"type": "string", "description": "the command to run"}},
            "required": ["command"],
        },
    },
}]


# --------------------------------------------------------------------------
# cases
# --------------------------------------------------------------------------

CASES: Dict[str, Dict[str, Any]] = {
    "trend_trust": {
        "prompt": (
            "We're thinking of adding an astronomy course to our education app. "
            "Is interest in astronomy growing in Ukrainian Wikipedia, and how much can "
            "we trust that signal?"
        ),
        "must_call": [r"wikitrends\.py\s+analyze", r"--langs\s+\S*uk"],
        "answer_must_mention": ["confidence", "share|edition|platform"],
        "answer_must_not_claim": [r"\bguarantee", r"proves? (?:demand|there is a market)"],
        "notes": "Real data shows a steep, genuine decline; the model must not report growth.",
    },
    "two_languages": {
        "prompt": (
            "Compare how interest in intermittent fasting has grown in Polish versus "
            "Czech Wikipedia over the last two years. Which is the better market?"
        ),
        "must_call": [r"wikitrends\.py\s+(analyze|resolve)"],
        "answer_must_mention": ["pol", "czech|cs|Přerušovaný"],
        "answer_must_not_claim": [r"\bproves\b"],
        # Polish has no such article at all; a good answer says so instead of inventing a number.
        "answer_should_flag_missing": True,
        "notes": "Polish Wikipedia has no article for this concept.",
    },
    "localisation": {
        "prompt": (
            "We're building a language-learning app and want to know which audiences to "
            "research next. Compare interest in learning English across the Ukrainian, "
            "Polish, Czech, German and Turkish Wikipedias, and give me a short shareable "
            "PDF report."
        ),
        "must_call": [r"wikitrends\.py\s+analyze", r"--langs\s+\S+,\S+"],
        "answer_must_mention": ["confidence", "share|edition|platform"],
        "answer_must_not_claim": [r"\bguarantee"],
        "must_produce_pdf": True,
        "notes": "Every edition's raw views fall; only Turkish holds share.",
    },
    "followup": {
        "prompt": (
            "Is interest in meditation growing in German Wikipedia? Use the last 3 years. "
            "Then also check Spanish and tell me which of the two looks better."
        ),
        "must_call": [r"wikitrends\.py\s+analyze"],
        "answer_must_mention": ["german|de", "spanish|es"],
        "answer_must_not_claim": [],
        "notes": "Tests a follow-up that widens the question; cache should make it fast.",
    },
}


# --------------------------------------------------------------------------
# model plumbing
# --------------------------------------------------------------------------

def call_model(messages: List[Dict], model: str, api_key: str) -> Dict:
    payload = {
        "model": model,
        "messages": messages,
        "tools": TOOLS,
        "temperature": 0,
        "max_tokens": 1200,
    }
    request = urllib.request.Request(
        API_URL,
        data=json.dumps(payload).encode(),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "X-Title": "wikipedia-topic-interest skill eval",
        },
    )
    for attempt in range(4):
        try:
            with urllib.request.urlopen(request, timeout=180) as response:
                return json.loads(response.read().decode())
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", "replace")[:300]
            if exc.code in (429, 500, 502, 503, 529) and attempt < 3:
                time.sleep(4 * (attempt + 1))
                continue
            raise SystemExit(f"OpenRouter HTTP {exc.code}: {body}")
        except urllib.error.URLError as exc:
            if attempt < 3:
                time.sleep(4 * (attempt + 1))
                continue
            raise SystemExit(f"OpenRouter unreachable: {exc.reason}")
    raise SystemExit("OpenRouter: retries exhausted")


def run_shell(command: str) -> str:
    """Execute a model-issued command inside the skill directory."""
    try:
        done = subprocess.run(
            command, shell=True, cwd=SKILL_ROOT, capture_output=True,
            text=True, timeout=COMMAND_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        return "ERROR: command timed out"
    output = (done.stdout or "") + (("\nSTDERR: " + done.stderr) if done.stderr.strip() else "")
    return output.strip()[:6000] or f"(no output, exit {done.returncode})"


# --------------------------------------------------------------------------
# grading
# --------------------------------------------------------------------------

def grade(case: Dict[str, Any], commands: List[str], answer: str, outputs: List[str]) -> List[Dict]:
    checks = []
    joined_commands = "\n".join(commands)
    lowered = answer.lower()

    def add(name: str, ok: bool, detail: str = ""):
        checks.append({"check": name, "ok": bool(ok), "detail": detail})

    add("used the skill CLI", bool(commands) and "wikitrends.py" in joined_commands,
        f"{len(commands)} command(s)")
    for pattern in case["must_call"]:
        add(f"command matches /{pattern}/", re.search(pattern, joined_commands) is not None)

    add("a run produced results",
        any("PERIOD" in out or '"series"' in out for out in outputs))
    add("no hand-rolled data work",
        not re.search(r"urllib|requests\.get|curl\s+http|import\s+statistics", joined_commands),
        "model should not bypass the skill")
    add("did not need more than 3 commands", len(commands) <= 3, f"{len(commands)} used")

    add("gave a written answer", len(answer.strip()) > 120, f"{len(answer)} chars")
    for phrase in case["answer_must_mention"]:
        add(f"answer mentions {phrase}", re.search(phrase, lowered) is not None)
    for pattern in case["answer_must_not_claim"]:
        add(f"answer avoids /{pattern}/", re.search(pattern, lowered) is None)

    # The caveat that pageviews are not demand must survive into the answer.
    add("answer keeps the demand caveat",
        any(word in lowered for word in
            ("not demand", "curiosity", "not proof", "validate", "interest \u2260", "does not mean")))

    if case.get("must_produce_pdf"):
        produced = any(".pdf" in out for out in outputs)
        add("produced a PDF", produced and os.path.exists(_newest_pdf() or ""), _newest_pdf() or "none")
    if case.get("answer_should_flag_missing"):
        add("flagged the missing Polish article",
            any(word in lowered for word in ("no article", "not exist", "no polish", "missing", "unavailable")))
    return checks


def _newest_pdf() -> Optional[str]:
    folder = os.path.join(SKILL_ROOT, "wikitrends-out")
    if not os.path.isdir(folder):
        return None
    pdfs = [os.path.join(folder, f) for f in os.listdir(folder) if f.endswith(".pdf")]
    return max(pdfs, key=os.path.getmtime) if pdfs else None


# --------------------------------------------------------------------------
# driver
# --------------------------------------------------------------------------

def run_case(name: str, case: Dict, model: str, api_key: str, python: str, verbose: bool) -> Dict:
    with open(os.path.join(SKILL_ROOT, "SKILL.md"), encoding="utf-8") as fh:
        skill_md = fh.read()

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT.format(
            root=SKILL_ROOT, skill=skill_md, python=python)},
        {"role": "user", "content": case["prompt"]},
    ]

    commands: List[str] = []
    outputs: List[str] = []
    answer = ""
    usage = {"prompt_tokens": 0, "completion_tokens": 0}
    started = time.time()

    for _ in range(MAX_TURNS):
        response = call_model(messages, model, api_key)
        for key in usage:
            usage[key] += response.get("usage", {}).get(key, 0) or 0
        choice = response["choices"][0]["message"]
        messages.append(choice)

        calls = choice.get("tool_calls") or []
        if not calls:
            answer = choice.get("content") or ""
            break

        for call in calls:
            try:
                command = json.loads(call["function"]["arguments"] or "{}").get("command", "")
            except json.JSONDecodeError:
                command = ""
            commands.append(command)
            if verbose:
                print(f"    $ {command}")
            output = run_shell(command) if command else "ERROR: no command given"
            outputs.append(output)
            if verbose:
                print("      " + output.replace("\n", "\n      ")[:700])
            messages.append({"role": "tool", "tool_call_id": call["id"],
                             "name": "shell", "content": output})

    checks = grade(case, commands, answer, outputs)
    return {
        "case": name,
        "passed": all(c["ok"] for c in checks),
        "checks": checks,
        "commands": commands,
        "answer": answer,
        "turns": len(commands),
        "seconds": round(time.time() - started, 1),
        "usage": usage,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate the skill against a real model.")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--case", action="append", choices=sorted(CASES), help="default: all")
    parser.add_argument("--python", default=os.path.join(SKILL_ROOT, ".venv", "bin", "python"),
                        help="interpreter the model is told to use")
    parser.add_argument("--out", help="write full results JSON here")
    parser.add_argument("-v", "--verbose", action="store_true", help="show commands and output")
    args = parser.parse_args()

    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        sys.stderr.write(
            "OPENROUTER_API_KEY is not set.\n"
            "Get a key at https://openrouter.ai/keys, then:\n"
            "  export OPENROUTER_API_KEY=sk-or-...\n"
        )
        return 2

    python = args.python if os.path.exists(args.python) else "python3"
    names = args.case or sorted(CASES)
    print(f"model={args.model}  python={python}  cases={', '.join(names)}\n")

    results = []
    for name in names:
        print(f"[{name}] {CASES[name]['prompt'][:78]}...")
        result = run_case(name, CASES[name], args.model, api_key, python, args.verbose)
        results.append(result)
        for check in result["checks"]:
            mark = "PASS" if check["ok"] else "FAIL"
            detail = f" ({check['detail']})" if check["detail"] else ""
            print(f"   {mark}  {check['check']}{detail}")
        cost_tokens = result["usage"]["prompt_tokens"] + result["usage"]["completion_tokens"]
        print(f"   -> {'PASSED' if result['passed'] else 'FAILED'} in {result['turns']} "
              f"command(s), {result['seconds']}s, {cost_tokens} tokens\n")

    passed = sum(1 for r in results if r["passed"])
    print(f"{passed}/{len(results)} cases passed")
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump({"model": args.model, "results": results}, fh, ensure_ascii=False, indent=2)
        print(f"details written to {args.out}")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
