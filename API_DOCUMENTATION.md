# Storybook Generation API Documentation

This document describes the current FastAPI server in [server.py](/c:/Users/user/Desktop/make_story/server.py).

## Version

- API version: `2.1.0`
- Base URL: `http://127.0.0.1:8000`
- Swagger UI: `http://127.0.0.1:8000/docs`
- OpenAPI JSON: `http://127.0.0.1:8000/openapi.json`

## What Changed In 2.1

- LLM dialogue output is now appended to `pages[].summary`.
- `pages[].dialogues` exposes structured dialogue data.
- `POST /api/runs` accepts optional `tts_config`.
- TTS can use a narrator voice and a separate dialogue voice.

## Request Model

### `POST /api/runs`

```json
{
  "era_ko": "조선 시대",
  "place_ko": "한양",
  "characters_ko": "호기심 많은 아이와 말하는 호랑이",
  "topic_ko": "서로를 믿는 우정",
  "tts_enabled": true,
  "tts_config": {
    "narrator_voice": "F2",
    "dialogue_voice": "F5",
    "character_voices": {
      "호랑이": "M3"
    },
    "lang": "ko",
    "speed": 1.05,
    "segment_pause_ms": 250
  }
}
```

### `tts_config` fields

- `narrator_voice`: voice for narration segments. Default `F2`
- `dialogue_voice`: default voice for dialogue segments. Default `F5`
- `character_voices`: optional per-character overrides
- `lang`: TTS language code. Default `ko`
- `speed`: TTS speed multiplier. Default `1.05`
- `segment_pause_ms`: silence inserted between synthesized segments. Default `250`

## Response Model

### `GET /api/runs/{run_id}`

```json
{
  "status": "RUNNING",
  "stage": "PANEL_2",
  "ready_max_page": 1,
  "ready_max_audio_page": 0,
  "pages": [
    {
      "page": 0,
      "title": "달빛 아래 작은 약속",
      "summary": "",
      "dialogues": [],
      "image_url": "/api/runs/20260316_120000_ab12cd/images/cover.png",
      "audio_url": "/api/runs/20260316_120000_ab12cd/audio/page_0.wav"
    },
    {
      "page": 1,
      "title": "",
      "summary": "아이는 달빛이 비추는 골목에서 길 잃은 호랑이를 만났어요.",
      "dialogues": [],
      "image_url": "/api/runs/20260316_120000_ab12cd/images/panel_1.png",
      "audio_url": "/api/runs/20260316_120000_ab12cd/audio/page_1.wav"
    },
    {
      "page": 2,
      "title": "",
      "summary": "아이는 호랑이에게 조심스럽게 다가갔어요.\n호랑이: \"무서워하지 마. 나는 길을 잃었어.\"",
      "dialogues": [
        {
          "character": "호랑이",
          "text": "무서워하지 마. 나는 길을 잃었어.",
          "voice": "F5"
        }
      ],
      "image_url": "/api/runs/20260316_120000_ab12cd/images/panel_2.png",
      "audio_url": "/api/runs/20260316_120000_ab12cd/audio/page_2.wav"
    }
  ],
  "error": null
}
```

### `PageInfo` fields

- `page`: page index `0..4`
- `title`: cover title
- `summary`: page text shown to clients. Dialogue lines are appended here when present.
- `dialogues`: structured dialogue list with resolved TTS voice
- `image_url`: image download path
- `audio_url`: audio download path

## Download Endpoints

- `GET /api/runs/{run_id}/images/{filename}`
- `GET /api/runs/{run_id}/audio/{filename}`

Image filenames:

- `cover.png`
- `panel_1.png` to `panel_4.png`

Audio filenames:

- `page_0.wav` to `page_4.wav`

## Notes

- Only one story generation run is processed at a time.
- If `tts_enabled=false`, audio URLs can stay empty.
- The current LLM schema still separates `summary` and `dialogue`.
- Because of that schema, audio is synthesized in this order:
  1. narration summary
  2. dialogue lines in array order

If you need exact in-story placement of narration and dialogue, move the LLM output to an ordered block schema such as:

```json
{
  "content_blocks": [
    { "type": "narration", "text": "..." },
    { "type": "dialogue", "character": "호랑이", "text": "..." }
  ]
}
```
