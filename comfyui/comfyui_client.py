"""
ComfyUI API client for programmatic workflow execution.

Handles:
- Loading and injecting workflow JSON
- POST /prompt to queue generation
- Polling /history/{prompt_id} until complete
- Fetching /view to download generated images
"""

import copy
import json
import time
import requests
from pathlib import Path
from typing import Dict, Any


class ComfyUIClient:
    """Client for interacting with ComfyUI REST API."""

    _ERROR_SNIPPET_LIMIT = 240
    _QUEUE_EXPECTED_NODES = ("8", "12")
    _IPADAPTER_NODES = ("10", "12", "14")
    _KSAMPLER_NODE = "1"
    _BASE_MODEL_NODE = "3"
    
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
        if reference_image is None:
            workflow = self._strip_ipadapter_nodes(workflow)
        elif "12" in workflow:
            workflow["12"]["inputs"]["image"] = reference_image
            workflow["12"]["inputs"]["upload"] = "input"
        
        return workflow

    @classmethod
    def _strip_ipadapter_nodes(cls, workflow: Dict[str, Any]) -> Dict[str, Any]:
        """Remove IPAdapter path and rewire KSampler to base model.

        When no reference image is available, the IPAdapter nodes (10, 12, 14)
        cannot execute. This strips them and points the KSampler model input
        directly at CheckpointLoaderSimple (node 3).
        """
        stripped = copy.deepcopy(workflow)
        for node_id in cls._IPADAPTER_NODES:
            stripped.pop(node_id, None)
        if cls._KSAMPLER_NODE in stripped:
            stripped[cls._KSAMPLER_NODE]["inputs"]["model"] = [cls._BASE_MODEL_NODE, 0]
        return stripped
    
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
        endpoint = "/prompt"
        workflow_summary = self._summarize_workflow(workflow)
        payload = {"prompt": workflow}
        try:
            response = requests.post(f"{self.base_url}{endpoint}", json=payload, timeout=10)
            response.raise_for_status()

            result = response.json()
            if not isinstance(result, dict):
                raise RuntimeError(
                    f"ComfyUI prompt queue malformed response at {endpoint}: "
                    f"response_type={type(result).__name__}; {workflow_summary}"
                )

            prompt_id = result.get("prompt_id")
            if not prompt_id:
                raise RuntimeError(
                    f"ComfyUI prompt queue missing prompt_id at {endpoint}: "
                    f"response_keys={sorted(result.keys())}; {workflow_summary}"
                )

            return prompt_id
        except requests.HTTPError as exc:
            status_code = getattr(exc.response, "status_code", "unknown")
            response_text = getattr(exc.response, "text", "")
            response_snippet = self._sanitize_error_snippet(response_text)
            prompt_id = self._extract_prompt_id_from_http_error(exc)

            prompt_context = f"prompt_id={prompt_id}; " if prompt_id else ""
            raise RuntimeError(
                f"ComfyUI prompt queue failed at {endpoint}: "
                f"{prompt_context}status={status_code}; "
                f"response_snippet={response_snippet}; {workflow_summary}"
            ) from exc
        except requests.RequestException as exc:
            raise RuntimeError(
                f"ComfyUI prompt queue failed at {endpoint}: {exc}; {workflow_summary}"
            ) from exc

    @classmethod
    def _sanitize_error_snippet(cls, body: Any) -> str:
        if body is None:
            return "<empty>"

        snippet = str(body).strip().replace("\n", " ")
        if not snippet:
            return "<empty>"

        if len(snippet) <= cls._ERROR_SNIPPET_LIMIT:
            return snippet

        return f"{snippet[:cls._ERROR_SNIPPET_LIMIT]}<truncated>"

    @classmethod
    def _summarize_workflow(cls, workflow: Any) -> str:
        if not isinstance(workflow, dict):
            return f"workflow=malformed workflow_type={type(workflow).__name__}"

        node_count = len(workflow)
        node_presence = [
            f"node_{node}={'present' if node in workflow else 'missing'}"
            for node in cls._QUEUE_EXPECTED_NODES
        ]
        return f"workflow_nodes={node_count} {' '.join(node_presence)}"

    @staticmethod
    def _extract_prompt_id_from_http_error(exc: requests.HTTPError) -> str | None:
        response = getattr(exc, "response", None)
        if response is None:
            return None

        try:
            payload = response.json()
        except Exception:
            return None

        if isinstance(payload, dict):
            prompt_id = payload.get("prompt_id")
            return str(prompt_id) if prompt_id else None

        return None

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
        
        try:
            prompt_id = self.queue_prompt(workflow)
        except RuntimeError as exc:
            raise RuntimeError(f"ComfyUI generate_image failed at queue_prompt: {exc}") from exc

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
