"""
HTTP client for llama-server
"""
import json
import requests
from typing import Optional


def call_llama_server(
    prompt: str,
    server_url: str = "http://127.0.0.1:8080",
    temperature: float = 0.3,
    top_p: float = 0.9,
    n_predict: int = 500,
) -> str:
    """Call llama-server with completion endpoint
    
    Args:
        prompt: Input prompt
        server_url: Server URL
        temperature: Temperature parameter
        top_p: Top-p parameter
        n_predict: Max tokens to generate
    
    Returns:
        Generated text
    """
    endpoint = f"{server_url}/completion"
    
    payload = {
        "prompt": prompt,
        "temperature": temperature,
        "top_p": top_p,
        "n_predict": n_predict,
        "stream": False,
        "grammar": None,  # Grammar is set in server startup
    }
    
    try:
        response = requests.post(endpoint, json=payload, timeout=300)
        response.raise_for_status()
        
        result = response.json()
        return result.get("content", "")
        
    except requests.exceptions.Timeout:
        raise RuntimeError("LLM server timeout (5 minutes)")
    except requests.exceptions.ConnectionError:
        raise RuntimeError(
            f"Cannot connect to LLM server at {server_url}. "
            "Make sure llama-server is running. See START_LLM_SERVER.md"
        )
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"LLM server request failed: {e}")
