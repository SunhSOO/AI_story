import json


def _extract_json_object_from(text: str, start: int) -> str:
    """Return the JSON substring that starts at the given '{' index."""
    in_str = False
    esc = False
    depth = 0

    for i in range(start, len(text)):
        c = text[i]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
            continue
        else:
            if c == '"':
                in_str = True
                continue
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    return text[start : i + 1]

    raise ValueError("Failed to find matching '}' for a JSON object.")


def extract_first_json_object(text: str) -> str:
    """Kept for backward compatibility; returns the first brace-balanced block."""
    start = text.find("{")
    if start == -1:
        raise ValueError("No '{' found in output.")
    return _extract_json_object_from(text, start)


def parse_json_strict(s: str) -> dict:
    """
    Scan through the text and return the first substring that parses as JSON.
    This skips instruction text that may contain '{' / '}' but is not JSON.
    """
    idx = s.find("{")
    last_err: Exception | None = None

    while idx != -1:
        try:
            candidate = _extract_json_object_from(s, idx)
            obj = json.loads(candidate)
            if isinstance(obj, dict) and "panels" in obj:
                return obj
            last_err = ValueError("JSON parsed but missing 'panels' key")
        except Exception as err:  # try the next '{' until success
            last_err = err
        idx = s.find("{", idx + 1)

    raise ValueError(f"Failed to parse JSON object. Last error: {last_err}")
