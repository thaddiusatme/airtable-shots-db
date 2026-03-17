"""
ComfyUI API client for programmatic workflow execution.

Handles:
- Loading and injecting workflow JSON
- POST /prompt to queue generation
- Polling /history/{prompt_id} until complete
- Fetching /view to download generated images
"""

import json
import time
import requests
from pathlib import Path
from typing import Dict, Any


class ComfyUIClient:
    """Client for interacting with ComfyUI REST API."""
    
    def __init__(self, base_url: str = "http://127.0.0.1:8188", timeout: int = 300):
        """
        Initialize ComfyUI client.
        
        Args:
            base_url: ComfyUI server URL (default: http://127.0.0.1:8188)
            timeout: Maximum seconds to wait for generation (default: 300)
        """
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
    
    def load_workflow(self, workflow_path: Path) -> Dict[str, Any]:
        """Load workflow JSON from file."""
        with open(workflow_path, 'r') as f:
            return json.load(f)
    
    def inject_prompt(
        self,
        workflow: Dict[str, Any],
        positive_prompt: str,
        negative_prompt: str,
        seed: int,
        width: int = 1024,
        height: int = 576,
        filename_prefix: str = "ComfyUI"
    ) -> Dict[str, Any]:
        """
        Inject storyboard parameters into workflow.
        
        Node IDs based on Storyboarder_api.json:
        - "4": CLIPTextEncode (positive prompt)
        - "5": CLIPTextEncode (negative prompt)
        - "1": KSampler (seed)
        - "6": EmptyLatentImage (width/height)
        - "8": SaveImage (filename_prefix)
        
        Args:
            workflow: Loaded workflow dict
            positive_prompt: Positive text prompt
            negative_prompt: Negative text prompt
            seed: Random seed for reproducibility
            width: Image width (default: 1024)
            height: Image height (default: 576)
            filename_prefix: Output filename prefix
            
        Returns:
            Modified workflow dict
        """
        workflow["4"]["inputs"]["text"] = positive_prompt
        workflow["5"]["inputs"]["text"] = negative_prompt
        workflow["1"]["inputs"]["seed"] = seed
        workflow["6"]["inputs"]["width"] = width
        workflow["6"]["inputs"]["height"] = height
        workflow["8"]["inputs"]["filename_prefix"] = filename_prefix
        
        return workflow
    
    def queue_prompt(self, workflow: Dict[str, Any]) -> str:
        """
        POST workflow to /prompt endpoint.
        
        Args:
            workflow: Workflow dict with injected parameters
            
        Returns:
            prompt_id for tracking generation status
            
        Raises:
            requests.RequestException: If API call fails
        """
        payload = {"prompt": workflow}
        response = requests.post(f"{self.base_url}/prompt", json=payload, timeout=10)
        response.raise_for_status()
        
        result = response.json()
        return result["prompt_id"]
    
    def poll_history(self, prompt_id: str, poll_interval: float = 1.0) -> Dict[str, Any]:
        """
        Poll /history/{prompt_id} until generation completes.
        
        Args:
            prompt_id: ID returned from queue_prompt
            poll_interval: Seconds between polls (default: 1.0)
            
        Returns:
            History entry for completed prompt
            
        Raises:
            TimeoutError: If generation exceeds self.timeout
            requests.RequestException: If API call fails
        """
        start_time = time.time()
        
        while True:
            elapsed = time.time() - start_time
            if elapsed > self.timeout:
                raise TimeoutError(f"ComfyUI generation exceeded {self.timeout}s timeout")
            
            response = requests.get(f"{self.base_url}/history/{prompt_id}", timeout=10)
            response.raise_for_status()
            
            history = response.json()
            
            if prompt_id in history:
                entry = history[prompt_id]
                if entry.get("status", {}).get("completed", False):
                    return entry
            
            time.sleep(poll_interval)
    
    def fetch_image(self, filename: str, subfolder: str = "", folder_type: str = "output") -> bytes:
        """
        Fetch generated image from /view endpoint.
        
        Args:
            filename: Image filename from history outputs
            subfolder: Optional subfolder path
            folder_type: Folder type (default: "output")
            
        Returns:
            Image bytes
            
        Raises:
            requests.RequestException: If download fails
        """
        params = {
            "filename": filename,
            "type": folder_type
        }
        if subfolder:
            params["subfolder"] = subfolder
        
        response = requests.get(f"{self.base_url}/view", params=params, timeout=30)
        response.raise_for_status()
        
        return response.content
    
    def generate_image(
        self,
        workflow_path: Path,
        positive_prompt: str,
        negative_prompt: str,
        seed: int,
        output_path: Path,
        width: int = 1024,
        height: int = 576
    ) -> Path:
        """
        End-to-end image generation: load workflow, inject params, queue, poll, download.
        
        Args:
            workflow_path: Path to workflow JSON
            positive_prompt: Positive text prompt
            negative_prompt: Negative text prompt
            seed: Random seed
            output_path: Where to save generated PNG
            width: Image width (default: 1024)
            height: Image height (default: 576)
            
        Returns:
            Path to saved image file
            
        Raises:
            TimeoutError: If generation times out
            requests.RequestException: If API calls fail
        """
        workflow = self.load_workflow(workflow_path)
        
        filename_prefix = output_path.stem
        workflow = self.inject_prompt(
            workflow,
            positive_prompt,
            negative_prompt,
            seed,
            width,
            height,
            filename_prefix
        )
        
        prompt_id = self.queue_prompt(workflow)
        history_entry = self.poll_history(prompt_id)
        
        outputs = history_entry.get("outputs", {})
        if not outputs:
            raise RuntimeError(f"No outputs in history for prompt_id={prompt_id}")
        
        save_image_node = outputs.get("8")
        if not save_image_node or "images" not in save_image_node:
            raise RuntimeError(f"No images in SaveImage node output for prompt_id={prompt_id}")
        
        image_info = save_image_node["images"][0]
        image_bytes = self.fetch_image(
            filename=image_info["filename"],
            subfolder=image_info.get("subfolder", ""),
            folder_type=image_info.get("type", "output")
        )
        
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(image_bytes)
        
        return output_path
