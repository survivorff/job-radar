"""Quick probe of a specific LLM model via the proxy."""

import os
import sys

from job_radar.llm import chat


def main() -> None:
    model = sys.argv[1] if len(sys.argv) > 1 else "deepseek-v4-flash"
    os.environ["JOB_RADAR_SCORER_MODEL"] = f"anthropic/{model}"
    r = chat(system="Reply in one word.", user="Say hi.", max_tokens=32)
    print(f"model:  {r.model}")
    print(f"text:   {r.text!r}")
    print(f"tokens: in={r.input_tokens} out={r.output_tokens}")


if __name__ == "__main__":
    main()
