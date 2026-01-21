def has_korean(text: str) -> bool:
    return any("\uac00" <= ch <= "\ud7a3" for ch in text)


def validate_panels(obj: dict):
    panels = obj.get("panels")
    assert isinstance(panels, list) and len(panels) == 5, "panels must be length 5 exactly"

    seen = set()
    for panel in panels:
        assert "panel" in panel and isinstance(panel["panel"], int), "panel must be int"
        idx = panel["panel"]
        assert idx in [0, 1, 2, 3, 4], "panel must be 0..4"
        assert idx not in seen, "duplicate panel index"
        seen.add(idx)

        prompt_value = panel.get("prompt", "").strip()
        assert prompt_value, f"panel{idx}.prompt empty"

        if idx == 0:
            assert panel.get("subject", "").strip(), "panel0.subject empty"
        else:
            summary_value = panel.get("summary", "").strip()
            assert summary_value, f"panel{idx}.summary empty"
            assert has_korean(summary_value), f"panel{idx}.summary should be Korean"


