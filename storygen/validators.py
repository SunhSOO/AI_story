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

            dialogue_items = panel.get("dialogue")
            if idx in [2, 3]:
                assert isinstance(dialogue_items, list) and dialogue_items, f"panel{idx}.dialogue must be a non-empty list"
                for dialogue_idx, item in enumerate(dialogue_items, start=1):
                    assert isinstance(item, dict), f"panel{idx}.dialogue[{dialogue_idx}] must be an object"
                    character_value = str(item.get("character", "")).strip()
                    text_value = str(item.get("text", "")).strip()
                    assert character_value, f"panel{idx}.dialogue[{dialogue_idx}].character empty"
                    assert text_value, f"panel{idx}.dialogue[{dialogue_idx}].text empty"
                    assert has_korean(text_value), f"panel{idx}.dialogue[{dialogue_idx}].text should be Korean"
            else:
                assert "dialogue" not in panel, f"panel{idx}.dialogue should not be present"

