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

    def upload_image(self, image_path: Path, subfolder: str = "", overwrite: bool = True) -> Dict[str, Any]:
        """Upload an image to ComfyUI's /upload/image endpoint.

        The returned payload contains the filename ComfyUI expects in LoadImage.
        """
        try:
            with open(image_path, "rb") as image_file:
                files = {"image": (image_path.name, image_file, "image/png")}
                data = {
                    "type": "input",
                    "subfolder": subfolder,
                    "overwrite": "true" if overwrite else "false",
                }
                response = requests.post(f"{self.base_url}/upload/image", files=files, data=data, timeout=30)
            response.raise_for_status()
            result = response.json()
            if not isinstance(result, dict) or "name" not in result:
                raise RuntimeError(f"Unexpected ComfyUI upload response: {result!r}")
            return result
        except requests.RequestException as exc:
            raise RuntimeError(f"ComfyUI image upload failed for {image_path.name}: {exc}") from exc
    
    def inject_prompt(
        self,
        workflow: Dict[str, Any],
        positive_prompt: str,
        negative_prompt: str,
        seed: int,
        width: int = 1024,
        height: int = 576,
        filename_prefix: str = "ComfyUI",
        reference_image: str | None = None,
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
        if reference_image is not None and "12" in workflow:
            workflow["12"]["inputs"]["image"] = reference_image
            workflow["12"]["inputs"]["upload"] = "input"
        
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
        try:
            response = requests.post(f"{self.base_url}/prompt", json=payload, timeout=10)
            response.raise_for_status()

            result = response.json()
            return result["prompt_id"]
        except requests.RequestException as exc:
            raise RuntimeError(f"ComfyUI prompt queue failed: {exc}") from exc

    @staticmethod
    def _summarize_history_state(history: Any, prompt_id: str) -> str:
        if not isinstance(history, dict):
            return f"history_state=malformed history_type={type(history).__name__}"

        if prompt_id not in history:
            return "history_state=missing"

        entry = history[prompt_id]
        if not isinstance(entry, dict):
            return f"history_state=malformed entry_type={type(entry).__name__}"

        status = entry.get("status")
        if not isinstance(status, dict):
            return f"history_state=incomplete status_type={type(status).__name__}"

        completed = status.get("completed")
        state = "complete" if completed is True else "incomplete"
        summary_parts = [f"history_state={state}", f"status.completed={completed!r}"]

        status_str = status.get("status_str")
        if status_str is not None:
            summary_parts.append(f"status.value={status_str!r}")

        outputs = entry.get("outputs")
        if isinstance(outputs, dict):
            summary_parts.append(f"outputs.nodes={len(outputs)}")
        elif outputs is not None:
            summary_parts.append(f"outputs_type={type(outputs).__name__}")

        return " ".join(summary_parts)
    
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
        last_summary = "history_state=unobserved"

        while True:
            elapsed = time.time() - start_time
            if elapsed > self.timeout:
                raise TimeoutError(
                    f"ComfyUI generation exceeded {self.timeout}s timeout "
                    f"for prompt_id={prompt_id} after {elapsed:.1f}s; {last_summary}"
                )

            try:
                response = requests.get(f"{self.base_url}/history/{prompt_id}", timeout=10)
                response.raise_for_status()
                history = response.json()
            except requests.RequestException as exc:
                raise RuntimeError(
                    f"ComfyUI poll_history failed for prompt_id={prompt_id} "
                    f"after {elapsed:.1f}s: {exc}"
                ) from exc

            last_summary = self._summarize_history_state(history, prompt_id)

            if isinstance(history, dict) and prompt_id in history:
                entry = history[prompt_id]
                if isinstance(entry, dict) and entry.get("status", {}).get("completed", False):
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
        
        try:
            response = requests.get(f"{self.base_url}/view", params=params, timeout=30)
            response.raise_for_status()
            return response.content
        except requests.RequestException as exc:
            raise RuntimeError(f"ComfyUI image fetch failed for {filename}: {exc}") from exc
    
    def generate_image(
        self,
        workflow_path: Path,
        positive_prompt: str,
        negative_prompt: str,
        seed: int,
        output_path: Path,
        width: int = 1024,
        height: int = 576,
        reference_image_path: Path | None = None,
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
        reference_image_name = None
        if reference_image_path is not None:
            uploaded = self.upload_image(reference_image_path)
            reference_image_name = uploaded["name"]
        workflow = self.inject_prompt(
            workflow,
            positive_prompt,
            negative_prompt,
            seed,
            width,
            height,
            filename_prefix,
            reference_image=reference_image_name,
        )
        
        prompt_id = self.queue_prompt(workflow)
        history_entry = self.poll_history(prompt_id)

        outputs = history_entry.get("outputs", {})
        if not outputs:
            raise RuntimeError(
                f"No outputs in history for prompt_id={prompt_id}; "
                f"history_status={history_entry.get('status')!r}"
            )

        save_image_node = outputs.get("8")
        if not save_image_node or "images" not in save_image_node:
            available_nodes = sorted(outputs.keys())
            raise RuntimeError(
                f"No images in SaveImage node output for prompt_id={prompt_id}; "
                f"available_output_nodes={available_nodes}"
            )

        images = save_image_node.get("images", [])
        if not images:
            raise RuntimeError(f"SaveImage node returned empty images list for prompt_id={prompt_id}")

        image_info = images[0]
        image_bytes = self.fetch_image(
            filename=image_info["filename"],
            subfolder=image_info.get("subfolder", ""),
            folder_type=image_info.get("type", "output")
        )
        
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(image_bytes)
        
        return output_path
