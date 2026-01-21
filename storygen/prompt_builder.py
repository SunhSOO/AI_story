# def build_prompt(era, place, characters, topic) -> str:
#     return f"""Output ONLY valid JSON. No markdown. No comments. No extra text.
# User inputs (Korean for story):
# - era: {era}
# - place: {place}
# - characters: {characters}
# - topic: {topic}

# CONTENT RULES:
# - panel 0:
#   - subject: Korean children's story title/subject (1 short phrase). Never empty.
#   - prompt: image prompt for a COVER (show main characters + background + era mood clearly).
# - panels 1..4:
#   - summary: Korean only, warm children's fairy tale tone, 1-2 short sentences. Never empty.
#   - Follow a clear arc:
#     1) 시작 배경  2) 문제  3) 해결 시도  4) 회복과 마무리
#   - prompt: image prompt that visually depicts the panel.

# IMAGE PROMPT RULES (for every "prompt" field):
# - Output format MUST be exactly:
#   "character(s), expression(1 word), situation(1 word), background(1 word)"
# - Exactly 4 comma-separated fields. No extra commas.
# - English ONLY. No Korean/Hangul characters.
# - VISUAL ONLY: no story explanation, no meta text.
# - character(s):
#   - Only 1-2 character names.
#   - If there are 2+ characters, join them with "+" inside the same field (do NOT add commas), e.g., "rabbit+fox".
# - expression:
#   - Exactly 1 word (e.g., happy, surprised, scared, excited, tense).
# - situation:
#   - Exactly 1 word (e.g., exploring, escaping, helping, reuniting, talking, swimming).
# - background:
#   - Exactly 1 word (e.g., ocean, forest, palace, village, cave).
# - Do NOT include: lighting, camera terms, style words, long location phrases, quotes, periods, extra adjectives.



# KID-STORY TONE (Korean summaries):
# - Use easy words, short sentences, gentle mood.
# - Prefer endings like "~했어요", "~하네요", "~해요", "~했단다"
# - Add a tiny playful onomatopoeia when natural.



# STRICT JSON RULES (must follow exactly):
# - Use EXACT structure and key order shown below.
# - Use double quotes for ALL keys and string values.
# - No trailing commas.
# - No extra keys anywhere.
# - panels must contain exactly 5 objects in this exact order (panel 0..4).
# - panel values must be integers 0,1,2,3,4 (unique).
# - Strings must not contain unescaped double quotes. If needed, escape with \\"
# - Do NOT include newline characters inside strings; keep strings as single-line text.

# OUTPUT MUST MATCH THIS EXACT SHAPE:
# {{
#   "panels": [
#     {{ "panel": 0, "subject": "...", "prompt": "..." }},
#     {{ "panel": 1, "summary": "...", "prompt": "..." }},
#     {{ "panel": 2, "summary": "...", "prompt": "..." }},
#     {{ "panel": 3, "summary": "...", "prompt": "..." }},
#     {{ "panel": 4, "summary": "...", "prompt": "..." }}
#   ]
# }}



# REMINDER:
# - Output JSON only. No leading/trailing text. No markdown.
# """

def build_prompt(era, place, characters, topic) -> str:
    return f"""Output ONLY valid JSON. No markdown. No comments. No extra text.
User inputs (Korean for story, English for prompt):
- era: {era}
- place: {place}
- characters: {characters}
- topic: {topic}

### 역할
너는 어린이 동화 작가이자 Stable Diffusion 프롬프트 전문가야. 사용자가 주는 이야기를 4개의 장면(Panel)으로 나누고, 각 장면을 위한 요약과 SD 전용 영어 프롬프트를 작성해야 해.

### 규칙
1. **Panel 0 (Subject):** 한글로 이야의 제목을 지어야해. (prompt): ** 제목의 프롬프트는 반드시 영어로 작성해야 해.
2. **Consistency (일관성):** Panel 1~4의 'prompt'에는 반드시 Panel 0에서 정의한 주인공의 특징과 화풍이 포함되어야 해.
3. **SD Prompt 형식:** 반드시 영어로 작성, 문장이 아닌, 쉼표로 구분된 단어(Tag) 위주로 작성해. (예: (masterpiece, best quality, 1girl, forest background, running...))
4. **언어:** 'summary'는 한국어로 동화체("~했어요,~했답니다")를 사용해, 'prompt'는 반드시 영어로 작성해.
5. 이야기는 다음과 같이 생성해줘 1)시작배경 2)문제발생 3) 해결 시도 4) 해결과 마무리
OUTPUT MUST MATCH THIS EXACT SHAPE:
{{
  "panels": [
    {{ "panel": 0, "subject": "동화제목", "prompt": "..." }},
    {{ "panel": 1, "summary": "동화내용", "prompt": "..." }},
    {{ "panel": 2, "summary": "동화내용", "prompt": "..." }},
    {{ "panel": 3, "summary": "동화내용", "prompt": "..." }},
    {{ "panel": 4, "summary": "동화내용", "prompt": "..." }}
  ]
}}



REMINDER:
- Output JSON only. No leading/trailing text. No markdown.
"""
