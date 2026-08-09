"""Optional LLM topic assignment for candidates the deterministic matcher
missed. Runs only when FIREWORKS_API_KEY is set; otherwise the deterministic
vocabulary matching is the whole story.

The LLM is constrained: it may ONLY pick terms from the vocabulary extracted
from the spreadsheet — it never invents or rephrases. It is the "understanding"
pass for stances like "housing crisis" when the sheet says "affordable housing".
"""

import json
import os
import urllib.request

MODEL = os.environ.get("TOPICS_LLM_MODEL", "accounts/fireworks/models/deepseek-v4-flash-0731")
API_URL = "https://api.fireworks.ai/inference/v1/chat/completions"
BATCH_SIZE = 20

SYSTEM_PROMPT = (
    "You assign issue tags to political candidates from their stances. "
    "You MUST only use terms from the provided vocabulary list, verbatim. "
    "Never invent, merge, or rephrase terms. If no vocabulary term applies, "
    "return an empty list. Reply with a single JSON object mapping each "
    "candidate name to its list of vocabulary terms."
)


def refine_with_llm(records, vocabulary):
    """Fill record['topics'] (vocabulary terms only) for candidates with none."""
    api_key = os.environ.get("FIREWORKS_API_KEY")
    if not api_key:
        return 0

    pending = [r for r in records if not r.get("topics")]
    if not pending:
        return 0

    assignments = {}
    for i in range(0, len(pending), BATCH_SIZE):
        batch = pending[i:i + BATCH_SIZE]
        assignments.update(classify_batch(batch, vocabulary, api_key))

    assigned = 0
    for record in records:
        if not record.get("topics") and record["name"] in assignments:
            record["topics"] = [t for t in assignments[record["name"]] if t in vocabulary]
            assigned += 1
    return assigned


def classify_batch(batch, vocabulary, api_key):
    payload = {
        "model": MODEL,
        "temperature": 0,
        "max_tokens": 4000,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"Vocabulary (use ONLY these, verbatim):\n{json.dumps(vocabulary)}\n\n"
                    "Candidates:\n" + json.dumps(
                        [{"name": r["name"], "stances": r["stances"]} for r in batch],
                        ensure_ascii=False,
                    )
                ),
            },
        ],
    }
    request = urllib.request.Request(
        API_URL,
        data=json.dumps(payload).encode(),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        body = json.load(response)
    content = body["choices"][0]["message"]["content"]
    return parse_assignments(content)


def parse_assignments(content):
    """Extract the JSON object from the model reply, tolerating markdown fences."""
    text = content.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end == -1:
            return {}
        parsed = json.loads(text[start:end + 1])
    return parsed if isinstance(parsed, dict) else {}
