"""
Async story generation pipeline orchestrator
"""
import asyncio
from pathlib import Path
from typing import Optional

from models import Status, Stage
from run_manager import RunManager, RunState
from pipeline.image_gen import generate_story_images
from pipeline.tts_gen import generate_page_audio

# Import existing story generation logic
from run_story import generate_story


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
        import subprocess
        import sys
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/F", "/IM", "llama-cli.exe"], 
                         capture_output=True, check=False)
        
        # 2. Free any GPU memory from previous image generation
        try:
             # We need to import ComfyUIClient here as it's not imported yet
            from pipeline.image_gen import ComfyUIClient
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, lambda: ComfyUIClient().free_memory())
            print("System cleaned up: LLM processes killed, GPU memory freed.")
        except Exception as e:
            print(f"Warning: Cleanup failed: {e}")

        
        # Stage 1: LLM - Generate story
        run_state.stage = Stage.LLM
        await run_manager.emit_event(run_id, {
            "status": run_state.status.value,
            "stage": run_state.stage.value,
            "ready_max_page": run_state.ready_max_page,
            "ready_max_audio_page": run_state.ready_max_audio_page
        })
        
        # Run LLM in executor to avoid blocking
        loop = asyncio.get_event_loop()
        story_obj = await loop.run_in_executor(
            None,
            generate_story,
            run_state.era,
            run_state.place,
            run_state.characters,
            run_state.topic
        )
        
        # Extract story content from storygen JSON structure
        # story_obj = {"panels": [{"panel": 0, "subject": "...", "prompt": "..."}, ...]}
        panels = story_obj.get("panels", [])
        
        # Panel 0 has "subject" (title), panels 1-4 have "summary" (content)
        cover_panel = next((p for p in panels if p.get("panel") == 0), {})
        cover_title = cover_panel.get("subject", "")
        cover_prompt = cover_panel.get("prompt", "")
        
        story_panels = [p for p in panels if p.get("panel") in [1, 2, 3, 4]]
        story_panels.sort(key=lambda x: x.get("panel", 0))
        
        # Update page content
        run_state.set_page_content(0, title=cover_title)
        for i, panel in enumerate(story_panels[:4], start=1):
            summary = panel.get("summary", "")
            run_state.set_page_content(i, summary=summary)
        
        # Stage 2-6: Generate images
        # Prepare prompts for image generation from "prompt" field
        panel_descriptions = []
        # Use cover prompt for panel 0
        panel_descriptions_all = [cover_prompt] + [p.get("prompt", "") for p in story_panels[:4]]
        
        # For story panels (1-4), use their prompts
        for panel in story_panels[:4]:
            desc = panel.get("prompt", "")
            panel_descriptions.append(desc)
        
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
            
            await loop.run_in_executor(
                None,
                generate_panel_image,
                prompt,
                seed,
                output_path,
                workflow_path,
                ComfyUIClient()
            )
            
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
        async def generate_single_audio(page_num: int, text: str):
            """Generate a single audio"""
            if not run_state.tts_enabled or not text.strip():
                return
                
            filename = await loop.run_in_executor(
                None,
                generate_page_audio,
                text,
                page_num,
                run_dir,
                "M2",
                "ko"
            )
            
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
        audio_coroutines.append(generate_single_audio(0, cover_title))
        
        # Panels 1-4 audio
        for i, summary in enumerate([p.get("summary", "") for p in story_panels[:4]], start=1):
            audio_coroutines.append(generate_single_audio(i, summary))
        
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
