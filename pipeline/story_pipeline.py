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
        
        # Stage 2-7: Generate images and TTS in parallel
        # This allows GPU (images) and CPU (TTS) to work simultaneously
        run_state.stage = Stage.COVER
        await run_manager.emit_event(run_id, {
            "status": run_state.status.value,
            "stage": run_state.stage.value,
            "ready_max_page": run_state.ready_max_page,
            "ready_max_audio_page": run_state.ready_max_audio_page
        })
        
        # Prepare image generation task
        async def generate_images():
            """Generate all images"""
            filenames = await loop.run_in_executor(
                None,
                generate_story_images,
                cover_prompt,
                panel_descriptions,
                run_dir,
                workflow_path
            )
            
            # Update URLs as images complete
            for page_num, filename in filenames.items():
                run_state.set_page_image(page_num, filename)
                
                # Update stage for panels
                if page_num == 1:
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
        
        # Prepare TTS generation task
        async def generate_audio():
            """Generate all audio"""
            if not run_state.tts_enabled:
                return
                
            # Use title for cover, summary for story panels
            audio_texts = [cover_title] + [p.get("summary", "") for p in story_panels[:4]]
            
            for page_num, text in enumerate(audio_texts):
                if text.strip():
                    filename = await loop.run_in_executor(
                        None,
                        generate_page_audio,
                        text,
                        page_num,
                        run_dir,
                        "M1",
                        "ko"
                    )
                    run_state.set_page_audio(page_num, filename)
                    
                    await run_manager.emit_event(run_id, {
                        "status": run_state.status.value,
                        "stage": run_state.stage.value,
                        "ready_max_page": run_state.ready_max_page,
                        "ready_max_audio_page": run_state.ready_max_audio_page
                    })
        
        # Run image and audio generation in parallel
        await asyncio.gather(
            generate_images(),
            generate_audio()
        )
        
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
        await run_manager.emit_event(run_id, {
            "status": run_state.status.value,
            "stage": run_state.stage.value,
            "ready_max_page": run_state.ready_max_page,
            "ready_max_audio_page": run_state.ready_max_audio_page,
            "error": str(e)
        })
