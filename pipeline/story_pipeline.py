"""
Async story generation pipeline orchestrator
"""
import asyncio
import time
from pathlib import Path
from typing import Optional

from models import DialogueLine, Status, Stage
from run_manager import RunManager, RunState
from pipeline.image_gen import generate_story_images
from pipeline.tts_gen import generate_page_audio

# Import existing story generation logic
from run_story import generate_story


def _resolve_dialogue_voice(run_state: RunState, character: str) -> str:
    return run_state.tts_config.character_voices.get(character, run_state.tts_config.dialogue_voice)


def _extract_dialogues(run_state: RunState, panel: dict) -> list[DialogueLine]:
    dialogues: list[DialogueLine] = []

    for item in panel.get("dialogue", []) or []:
        character = str(item.get("character", "")).strip()
        text = str(item.get("text", "")).strip()
        if not character or not text:
            continue

        dialogues.append(
            DialogueLine(
                character=character,
                text=text,
                voice=_resolve_dialogue_voice(run_state, character),
            )
        )

    return dialogues


def _build_page_text(summary: str, dialogues: list[DialogueLine]) -> str:
    parts = []
    if summary.strip():
        parts.append(summary.strip())

    for dialogue in dialogues:
        parts.append(f'{dialogue.character}: "{dialogue.text}"')

    return "\n".join(parts)


async def run_story_pipeline(run_id: str, run_manager: RunManager):
    """Execute the complete story generation pipeline
    
    Pipeline stages:
    1. LLM - Generate story structure
    2. COVER - Generate cover image
    3. PANEL_1-4 - Generate panel images
    4. TTS - Generate audio for all pages
    
    Args:
        run_id: Run identifier
        run_manager: Run manager instance
    """
    run_state = run_manager.get_run(run_id)
    if not run_state:
        return
    
    run_dir = run_manager.get_run_dir(run_id)
    # make_panel.json is in project root, not pipeline folder
    workflow_path = Path(__file__).parent.parent / "make_panel.json"
    loop = asyncio.get_event_loop()

    async def cleanup_system_state(reason: str):
        """Best-effort cleanup so the next run starts from a known-good state."""
        print(f"[CLEANUP] Resetting system state ({reason})...")

        try:
            from pipeline.image_gen import ComfyUIClient
            await loop.run_in_executor(None, lambda: ComfyUIClient().free_memory())
        except Exception as e:
            print(f"[CLEANUP] ComfyUI memory cleanup failed: {e}")

        try:
            import gc
            import torch

            gc.collect()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                torch.cuda.synchronize()
        except Exception as e:
            print(f"[CLEANUP] Torch CUDA cleanup failed: {e}")

        try:
            import subprocess
            import sys

            if sys.platform == "win32":
                subprocess.run(
                    ["taskkill", "/F", "/IM", "llama-cli.exe"],
                    capture_output=True,
                    check=False
                )
        except Exception as e:
            print(f"[CLEANUP] LLM process cleanup failed: {e}")
    
    try:
        # Update status to RUNNING
        run_state.status = Status.RUNNING
        await run_manager.emit_event(run_id, {
            "status": run_state.status.value,
            "stage": run_state.stage.value,
            "ready_max_page": run_state.ready_max_page,
            "ready_max_audio_page": run_state.ready_max_audio_page
        })
        
        # SYSTEM CLEANUP: Force clean state before starting
        # 1. Kill any zombie LLM processes
        await cleanup_system_state("before pipeline start")
        print("System cleaned up: LLM processes killed, GPU memory freed.")

        
        # Stage 1: LLM - Generate story
        run_state.stage = Stage.LLM
        await run_manager.emit_event(run_id, {
            "status": run_state.status.value,
            "stage": run_state.stage.value,
            "ready_max_page": run_state.ready_max_page,
            "ready_max_audio_page": run_state.ready_max_audio_page
        })
        
        # Run LLM in executor to avoid blocking
        print(f"\n[TIMING] Starting LLM generation for run {run_id}...")
        llm_start = time.time()
        story_obj = await loop.run_in_executor(
            None,
            generate_story,
            run_state.era,
            run_state.place,
            run_state.characters,
            run_state.topic
        )
        llm_end = time.time()
        print(f"[TIMING] LLM generation completed in {llm_end - llm_start:.2f}s")
        
        # Extract story content from storygen JSON structure
        # story_obj = {"panels": [{"panel": 0, "subject": "...", "prompt": "..."}, ...]}
        panels = story_obj.get("panels", [])
        
        # Panel 0 has "subject" (title), panels 1-4 have "summary" and optional dialogue.
        cover_panel = next((p for p in panels if p.get("panel") == 0), {})
        cover_title = cover_panel.get("subject", "")
        cover_prompt = cover_panel.get("prompt", "")
        
        story_panels = [p for p in panels if p.get("panel") in [1, 2, 3, 4]]
        story_panels.sort(key=lambda x: x.get("panel", 0))
        
        prepared_story_panels = []

        # Update page content
        run_state.set_page_content(0, title=cover_title, dialogues=[])
        for panel in story_panels[:4]:
            page_num = panel.get("panel", 0)
            summary = str(panel.get("summary", "")).strip()
            dialogues = _extract_dialogues(run_state, panel)
            page_text = _build_page_text(summary, dialogues)

            prepared_story_panels.append({
                "page_num": page_num,
                "prompt": panel.get("prompt", ""),
                "summary": summary,
                "content": page_text,
                "dialogues": dialogues,
            })
            run_state.set_page_content(page_num, summary=page_text, dialogues=dialogues)
        
        # Stage 2-6: Generate images
        # Prepare prompts for image generation from "prompt" field
        panel_descriptions = [panel["prompt"] for panel in prepared_story_panels]
        
        # Generate all images (cover + 4 panels)
        # For now, we'll do this synchronously but update stage for each
        
        # COVER
        run_state.stage = Stage.COVER
        await run_manager.emit_event(run_id, {
            "status": run_state.status.value,
            "stage": run_state.stage.value,
            "ready_max_page": run_state.ready_max_page,
            "ready_max_audio_page": run_state.ready_max_audio_page
        })
        
        # Stage 2-7: Generate images and TTS in true parallel
        # This allows GPU (images) and CPU (TTS) to work simultaneously from the start
        run_state.stage = Stage.COVER
        await run_manager.emit_event(run_id, {
            "status": run_state.status.value,
            "stage": run_state.stage.value,
            "ready_max_page": run_state.ready_max_page,
            "ready_max_audio_page": run_state.ready_max_audio_page
        })
        
        # Import for image generation
        from pipeline.image_gen import ComfyUIClient, generate_panel_image
        import random
        
        # Generate random seed for consistency
        base_seed = random.randint(0, 9999999)
        
        # Prepare all image generation tasks
        async def generate_single_image(page_num: int, prompt: str, seed: int):
            """Generate a single image"""
            filename = f"cover.png" if page_num == 0 else f"panel_{page_num}.png"
            output_path = run_dir / filename
            
            page_name = "Cover" if page_num == 0 else f"Panel {page_num}"
            print(f"[TIMING] Starting {page_name} image generation...")
            img_start = time.time()
            
            await loop.run_in_executor(
                None,
                generate_panel_image,
                prompt,
                seed,
                output_path,
                workflow_path,
                ComfyUIClient()
            )
            
            img_end = time.time()
            print(f"[TIMING] {page_name} image completed in {img_end - img_start:.2f}s")
            
            run_state.set_page_image(page_num, filename)
            
            # Update stage
            if page_num == 0:
                run_state.stage = Stage.COVER
            elif page_num == 1:
                run_state.stage = Stage.PANEL_1
            elif page_num == 2:
                run_state.stage = Stage.PANEL_2
            elif page_num == 3:
                run_state.stage = Stage.PANEL_3
            elif page_num == 4:
                run_state.stage = Stage.PANEL_4
            
            await run_manager.emit_event(run_id, {
                "status": run_state.status.value,
                "stage": run_state.stage.value,
                "ready_max_page": run_state.ready_max_page,
                "ready_max_audio_page": run_state.ready_max_audio_page
            })
        
        # Prepare all audio generation tasks
        async def generate_single_audio(page_num: int, summary_text: str, dialogues: Optional[list[DialogueLine]] = None):
            """Generate a single audio"""
            has_dialogue = any(dialogue.text.strip() for dialogue in (dialogues or []))
            if not run_state.tts_enabled or (not summary_text.strip() and not has_dialogue):
                return
            
            page_name = "Cover" if page_num == 0 else f"Page {page_num}"
            print(f"[TIMING] Starting {page_name} audio generation...")
            audio_start = time.time()
                
            filename = await loop.run_in_executor(
                None,
                generate_page_audio,
                summary_text,
                [dialogue.model_dump() for dialogue in (dialogues or [])],
                page_num,
                run_dir,
                run_state.tts_config.model_dump()
            )
            
            audio_end = time.time()
            print(f"[TIMING] {page_name} audio completed in {audio_end - audio_start:.2f}s")
            
            run_state.set_page_audio(page_num, filename)
            
            await run_manager.emit_event(run_id, {
                "status": run_state.status.value,
                "stage": run_state.stage.value,
                "ready_max_page": run_state.ready_max_page,
                "ready_max_audio_page": run_state.ready_max_audio_page
            })
        
        # Start audio generation in background immediately
        # Create tasks from coroutines and start them
        audio_coroutines = []
        
        # Cover (page 0) audio
        audio_coroutines.append(generate_single_audio(0, cover_title, []))
        
        # Panels 1-4 audio
        for panel in prepared_story_panels:
            audio_coroutines.append(
                generate_single_audio(panel["page_num"], panel["summary"], panel["dialogues"])
            )
        
        # Start all audio tasks in background
        if audio_coroutines:
            audio_gathering_task = asyncio.gather(*audio_coroutines)
        else:
            audio_gathering_task = None
        
        # Run image tasks SEQUENTIALLY (Cover -> Panel 1-4)
        # Cover (page 0)
        await generate_single_image(0, cover_prompt, base_seed)
        
        # Panels 1-4
        for i, prompt in enumerate(panel_descriptions, start=1):
            await generate_single_image(i, prompt, base_seed)
            
        # Free GPU memory after all images are generated
        try:
            await loop.run_in_executor(None, lambda: ComfyUIClient().free_memory())
        except Exception as e:
            print(f"Failed to free GPU memory: {e}")

        # Wait for audio to finish if it hasn't already
        if audio_gathering_task is not None:
            await audio_gathering_task
        
        # Update final stage
        run_state.stage = Stage.TTS
        await run_manager.emit_event(run_id, {
            "status": run_state.status.value,
            "stage": run_state.stage.value,
            "ready_max_page": run_state.ready_max_page,
            "ready_max_audio_page": run_state.ready_max_audio_page
        })
        
        # Mark as DONE
        run_state.status = Status.DONE
        await run_manager.emit_event(run_id, {
            "status": run_state.status.value,
            "stage": run_state.stage.value,
            "ready_max_page": run_state.ready_max_page,
            "ready_max_audio_page": run_state.ready_max_audio_page
        })
        
    except Exception as e:
        await cleanup_system_state("pipeline failure")

        # Mark as FAILED
        run_state.status = Status.FAILED
        run_state.error = str(e)
        import traceback
        traceback.print_exc()
        print(f"Pipeline Error: {e}")
        await run_manager.emit_event(run_id, {
            "status": run_state.status.value,
            "stage": run_state.stage.value,
            "ready_max_page": run_state.ready_max_page,
            "ready_max_audio_page": run_state.ready_max_audio_page,
            "error": str(e)
        })
    finally:
        await cleanup_system_state("pipeline end")

