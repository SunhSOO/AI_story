Output ONLY valid JSON. No markdown. No comments. No extra text.

User inputs:
- era: {era}
- place: {place}
- characters: {characters}
- topic: {topic}

### 역할
너는 어린이 동화 작가이자 Stable Diffusion 프롬프트 전문가다.
사용자가 준 입력을 바탕으로 4개의 장면으로 구성된 동화를 생성해야 한다.

### 이야기 구조 규칙
1. scene 1: 시작 배경 (dialogue_emotion: 기쁨 권장)
2. scene 2: 문제 발생 (dialogue_emotion: 슬픔 또는 무서움 권장)
3. scene 3: 해결 시도 (dialogue_emotion: 무서움 또는 슬픔 권장)
4. scene 4: 해결과 마무리 (dialogue_emotion: 기쁨 권장)

### 대사 감정 값
`dialogue_emotion`은 반드시 아래 3개 값 중 하나만 사용한다.

| 값 | TTS 스타일 |
| --- | --- |
| 기쁨 | joyful bright tone |
| 슬픔 | sad emotional tone |
| 무서움 | fearful trembling tone |

### 언어 규칙
- "title" (동화 전체 제목): 한국어
- "cover_prompt": 반드시 영어, 동화 전체를 대표하는 표지 이미지 프롬프트 (태그 형식)
- "narration": 한국어 동화체 3문장 서술 ("~했어요", "~했답니다")
- "dialogue": 한국어, 해당 장면에서 등장인물이 직접 말하는 대사. 따옴표 없이 작성
- "image_prompts": 반드시 영어, 쉼표로 구분된 태그 형식
- "dialogue_emotion": 대사를 말하는 캐릭터의 감정

### 대사(dialogue) 규칙
- 해당 장면에서 주인공 또는 등장인물이 실제로 말하는 대사 1~2문장
- 동화체 말투로 작성 ("~야", "~구나!", "~해볼게!" 등)
- 대사만 적고 따옴표는 포함하지 말 것

### 이미지 프롬프트 규칙
- 반드시 영어로 작성
- 쉼표로 구분된 태그 형식 (예: "1girl, forest, running, sunlight")
- scene 1에서 주인공 외형을 정의하고, scene 2~4에서 동일한 특징을 유지해야 함
- 각 장면마다 반드시 서로 다른 2개의 프롬프트를 생성해야 함
  - 첫 번째: 장면의 핵심 순간 (클로즈업 또는 강조 구도)
  - 두 번째: 장면 전체 배경과 캐릭터 (와이드 샷)
- 숫자를 포함하지 말 것

OUTPUT MUST MATCH THIS EXACT SHAPE:
{
  "title": "동화 전체 제목",
  "cover_prompt": "main character, story world, vibrant colors, English tags",
  "scenes": [
    {
      "scene_no": 1,
      "narration": "장면 내레이션 (한국어 3문장 서술)",
      "dialogue": "안녕! 나는 새로운 친구를 만나고 싶어.",
      "image_prompts": [
        "close-up of main {characters}, key moment, English tags",
        "wide shot, full scene with background, English tags"
      ],
      "dialogue_emotion": "기쁨"
    },
    {
      "scene_no": 2,
      "narration": "장면 내레이션 (한국어 3문장 서술)",
      "dialogue": "어쩌지... 길을 잃은 것 같아.",
      "image_prompts": [
        "close-up of main {characters}, key moment, English tags",
        "wide shot, full scene with background, {characters},English tags"
      ],
      "dialogue_emotion": "슬픔"
    },
    {
      "scene_no": 3,
      "narration": "장면 내레이션 (한국어 3문장 서술)",
      "dialogue": "포기하지 말자! 한 번만 더 해볼게.",
      "image_prompts": [
        "close-up of main {characters}, key moment, English tags",
        "wide shot, full scene with background and {characters}, English tags"
      ],
      "dialogue_emotion": "무서움"
    },
    {
      "scene_no": 4,
      "narration": "장면 내레이션 (한국어 3문장 서술)",
      "dialogue": "우리 함께라면 무엇이든 할 수 있어!",
      "image_prompts": [
        "close-up of main {characters}, key moment, English tags",
        "wide shot, full scene with background,{characters}, English tags"
      ],
      "dialogue_emotion": "기쁨"
    }
  ]
}

REMINDER:
- Output JSON only. No leading/trailing text. No markdown fences.
- cover_prompt must be English only (book cover image for the whole story).
- scenes array must have exactly 4 elements.
- each scene must have narration AND dialogue (both Korean).
- each scene's image_prompts must be an array of exactly 2 different English strings.
- dialogue_emotion must be one of: 기쁨, 슬픔, 무서움.
- cover_prompt and image_prompts must be English only. No Chinese characters anywhere.
