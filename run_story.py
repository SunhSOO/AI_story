import json
from storygen import (
    RAW_OUTPUT_PATH,
    SPEC_OUTPUT_PATH,
    USE_GRAMMAR,
    build_prompt,
    extract_first_json_object,
    parse_json_strict,
    run_llama_stream,
    validate_panels,
)


def generate_story(era: str, place: str, characters: str, topic: str) -> dict:
    prompt = build_prompt(era, place, characters, topic)
    prompt_for_attempt = prompt
    last_error = None

    for attempt in range(3):
        try:
            print(f"\n\n=== attempt {attempt + 1}/3 (USE_GRAMMAR={USE_GRAMMAR}) ===\n")
            raw_output = run_llama_stream(prompt_for_attempt)
            try:
                json_text = extract_first_json_object(raw_output)
                RAW_OUTPUT_PATH.write_text(json_text, encoding="utf-8", errors="ignore")
            except Exception:
                # Fall back to saving the full raw output for debugging.
                RAW_OUTPUT_PATH.write_text(raw_output, encoding="utf-8", errors="ignore")
                raise

            story_obj = parse_json_strict(json_text)
            validate_panels(story_obj)
            return story_obj
        except Exception as err:
            last_error = err
            print("\n[ERROR]", repr(err))
            print(f"Saved raw output to: {RAW_OUTPUT_PATH}")

            # Do not retry if prompt-language assertion triggers.
            if isinstance(err, AssertionError) and "prompt should be English only" in str(err):
                raise

            prompt_for_attempt = "REMINDER: Do NOT leave any field empty. Output ONLY the JSON object.\n" + prompt_for_attempt

    raise RuntimeError(f"Failed after retries: {last_error}")


def main():
    print("=== 4-cut Story Panel Generator ===")
    era = input("시대: ").strip()
    place = input("장소: ").strip()
    characters = input("주인공: ").strip()
    topic = input("주제: ").strip()

    story_obj = generate_story(era, place, characters, topic)

    SPEC_OUTPUT_PATH.write_text(json.dumps(story_obj, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\nOK: wrote spec.json\n")
    print("Saved to:", str(SPEC_OUTPUT_PATH.resolve()))


if __name__ == "__main__":
    main()
