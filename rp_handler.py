import time
import requests
import runpod
import json
import urllib.parse
import base64
import random
import os

# ---------------------------------------------------------------------------- #
#                                Configuration                                 #
# ---------------------------------------------------------------------------- #
COMFY_URL = "http://127.0.0.1:8188"

# Node IDs from workflow_api.json
NODE_ID_POSITIVE_PROMPT = "7"    # CLIPTextEncode (Positive)
NODE_ID_NEGATIVE_PROMPT = "8"    # CLIPTextEncode (Negative)
NODE_ID_LOAD_IMAGE      = "5"   # LoadImage
NODE_ID_RESIZE           = "6"   # ImageResizeKJv2
NODE_ID_PAINTER_I2V      = "15"  # PainterI2VAdvanced
NODE_ID_KSAMPLER_HIGH    = "16"  # KSamplerAdvanced (First Pass)
NODE_ID_KSAMPLER_LOW     = "18"  # KSamplerAdvanced (Second Pass)
NODE_ID_VIDEO_OUTPUT     = "21"  # VHS_VideoCombine
NODE_ID_SHARPEN          = "20"  # FastUnsharpSharpen
NODE_ID_VIDEO_COMBINE    = "21"  # VHS_VideoCombine

# Max time to wait for ComfyUI startup (seconds)
COMFY_STARTUP_TIMEOUT = 120
# Max time to wait for video generation (seconds) — WAN 14B can be slow
GENERATION_TIMEOUT = 3600


def check_server(url, timeout=COMFY_STARTUP_TIMEOUT):
    """Wait for ComfyUI to start up."""
    retries = 0
    while retries < timeout:
        try:
            requests.get(url, timeout=2)
            return True
        except requests.exceptions.ConnectionError:
            retries += 1
            time.sleep(1)
    return False


def upload_image(image_b64, filename="input.png"):
    """Upload a base64-encoded image to ComfyUI's input folder."""
    image_bytes = base64.b64decode(image_b64)

    # Use ComfyUI's upload endpoint
    files = {
        "image": (filename, image_bytes, "image/png"),
    }
    data = {
        "overwrite": "true",
    }
    response = requests.post(f"{COMFY_URL}/upload/image", files=files, data=data)
    response.raise_for_status()
    result = response.json()
    return result.get("name", filename)


def handler(job):
    job_input = job["input"]

    # ------------------------------------------------------------------ #
    # 1. Wait for ComfyUI
    # ------------------------------------------------------------------ #
    if not check_server(COMFY_URL):
        return {"error": "ComfyUI failed to start"}

    # ------------------------------------------------------------------ #
    # 2. Load the baked-in workflow
    # ------------------------------------------------------------------ #
    with open("/workflow_api.json", "r") as f:
        workflow = json.load(f)

    # ------------------------------------------------------------------ #
    # 3. Validate required input — image is mandatory for I2V
    # ------------------------------------------------------------------ #
    if "image" not in job_input:
        return {"error": "Missing required field: 'image' (base64-encoded PNG/JPG)"}

    # ------------------------------------------------------------------ #
    # 4. Upload the input image
    # ------------------------------------------------------------------ #
    try:
        uploaded_name = upload_image(job_input["image"])
        workflow[NODE_ID_LOAD_IMAGE]["inputs"]["image"] = uploaded_name
    except Exception as e:
        return {"error": f"Failed to upload image: {str(e)}"}

    # ------------------------------------------------------------------ #
    # 5. Inject user parameters
    # ------------------------------------------------------------------ #

    # -- Positive prompt --
    if "prompt" in job_input:
        workflow[NODE_ID_POSITIVE_PROMPT]["inputs"]["text"] = job_input["prompt"]

    # -- Negative prompt --
    if "negative_prompt" in job_input:
        workflow[NODE_ID_NEGATIVE_PROMPT]["inputs"]["text"] = job_input["negative_prompt"]

    # -- Seed (applied to both KSamplers) --
    seed = job_input.get("seed", random.randint(0, 2**53))
    workflow[NODE_ID_KSAMPLER_HIGH]["inputs"]["noise_seed"] = seed
    workflow[NODE_ID_KSAMPLER_LOW]["inputs"]["noise_seed"] = seed

    # -- Steps (applied to both KSamplers) --
    if "steps" in job_input:
        workflow[NODE_ID_KSAMPLER_HIGH]["inputs"]["steps"] = job_input["steps"]
        workflow[NODE_ID_KSAMPLER_LOW]["inputs"]["steps"] = job_input["steps"]

    # -- Split step (first pass end / second pass start) --
    if "split_step" in job_input:
        workflow[NODE_ID_KSAMPLER_HIGH]["inputs"]["end_at_step"] = job_input["split_step"]
        workflow[NODE_ID_KSAMPLER_LOW]["inputs"]["start_at_step"] = job_input["split_step"]

    # -- Video length (number of frames) --
    if "length" in job_input:
        workflow[NODE_ID_PAINTER_I2V]["inputs"]["length"] = job_input["length"]

    # -- Motion amplitude --
    if "motion_amplitude" in job_input:
        workflow[NODE_ID_PAINTER_I2V]["inputs"]["motion_amplitude"] = job_input["motion_amplitude"]

    # -- Image resize dimensions --
    if "width" in job_input:
        workflow[NODE_ID_RESIZE]["inputs"]["width"] = job_input["width"]
    if "height" in job_input:
        workflow[NODE_ID_RESIZE]["inputs"]["height"] = job_input["height"]

    # -- Frame rate --
    if "frame_rate" in job_input:
        workflow[NODE_ID_VIDEO_COMBINE]["inputs"]["frame_rate"] = job_input["frame_rate"]

    # -- Sharpen strength --
    if "sharpen_strength" in job_input:
        workflow[NODE_ID_SHARPEN]["inputs"]["strength"] = job_input["sharpen_strength"]

    # ------------------------------------------------------------------ #
    # 6. Queue the prompt in ComfyUI
    # ------------------------------------------------------------------ #
    try:
        response = requests.post(f"{COMFY_URL}/prompt", json={"prompt": workflow})
        response.raise_for_status()
        prompt_id = response.json()["prompt_id"]
    except Exception as e:
        return {"error": f"Failed to queue prompt: {str(e)}"}

    # ------------------------------------------------------------------ #
    # 7. Poll for completion
    # ------------------------------------------------------------------ #
    start_time = time.time()
    while True:
        if time.time() - start_time > GENERATION_TIMEOUT:
            return {"error": f"Generation timed out after {GENERATION_TIMEOUT}s"}

        try:
            history_url = f"{COMFY_URL}/history/{prompt_id}"
            res = requests.get(history_url)
            history = res.json()
        except Exception:
            time.sleep(2)
            continue

        if prompt_id in history:
            # Check for errors
            status = history[prompt_id].get("status", {})
            if status.get("status_str") == "error":
                messages = status.get("messages", [])
                return {"error": f"ComfyUI execution error: {messages}"}

            outputs = history[prompt_id].get("outputs", {})
            output_data = outputs.get(NODE_ID_VIDEO_OUTPUT)

            if output_data:
                # VHS_VideoCombine stores output under "gifs" key (even for mp4)
                videos = output_data.get("gifs", [])
                if videos:
                    video_info = videos[0]
                    filename = video_info["filename"]
                    subfolder = video_info.get("subfolder", "")
                    type_ = video_info.get("type", "output")

                    # Download video from ComfyUI
                    params = {"filename": filename, "subfolder": subfolder, "type": type_}
                    video_url = f"{COMFY_URL}/view?{urllib.parse.urlencode(params)}"
                    video_bytes = requests.get(video_url).content
                    video_b64 = base64.b64encode(video_bytes).decode("utf-8")

                    return {
                        "video": video_b64,
                        "filename": filename,
                        "seed": seed,
                    }
                else:
                    return {"error": "No video generated"}
            else:
                return {"error": "No output from VHS_VideoCombine node"}

        time.sleep(2)


runpod.serverless.start({"handler": handler})
