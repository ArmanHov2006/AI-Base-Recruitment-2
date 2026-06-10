"""One-off helper to split prompts out of ollama.py."""
from pathlib import Path

root = Path(__file__).resolve().parents[1]
src = (root / "app/llm/ollama.py").read_text(encoding="utf-8")
lines = src.splitlines()
start = next(i for i, line in enumerate(lines) if line.startswith("_EXTRACT_PROMPT"))
end = next(i for i, line in enumerate(lines) if line.startswith("class OllamaClient"))
header = (
    '"""Shared LLM prompts and formatting helpers."""\n\n'
    "from app.parser.schemas import CandidateData\n\n"
)
(root / "app/llm/prompts.py").write_text(header + "\n".join(lines[start:end]) + "\n", encoding="utf-8")
print(f"Wrote app/llm/prompts.py ({end - start} lines)")
