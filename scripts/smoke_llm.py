"""Smoke-test the Anthropic-compatible LLM proxy."""

from job_radar.llm import chat, estimate_cost_cny


def main() -> None:
    r = chat(
        system="You reply in one short sentence.",
        user="What is 2+2? Answer as a single number.",
        max_tokens=50,
    )
    print(f"text: {r.text!r}")
    print(f"model: {r.model}")
    print(f"tokens: in={r.input_tokens} out={r.output_tokens}")
    print(f"est cost (CNY): {estimate_cost_cny(r):.5f}")


if __name__ == "__main__":
    main()
