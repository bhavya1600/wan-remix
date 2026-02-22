FROM runpod/worker-comfyui:5.7.1-base

# 1. GPU SETUP
ENV NVIDIA_VISIBLE_DEVICES=all
ENV NVIDIA_DRIVER_CAPABILITIES=compute,utility

# ---------------------------------------------------------------------------- #
# 2. INSTALL CUSTOM NODES
# ---------------------------------------------------------------------------- #
# KJNodes — ImageResizeKJv2, VRAM_Debug
RUN comfy node install --exit-on-fail comfyui-kjnodes

# Video Helper Suite — VHS_VideoCombine
RUN comfy node install --exit-on-fail comfyui-videohelpersuite

# Aspect Ratio / Crop / Sharpen — FastUnsharpSharpen
RUN comfy node install --exit-on-fail comfyui-aspect-ratio-crop-node

# PainterI2VAdvanced — Image-to-Video conditioning
RUN cd /comfyui/custom_nodes && \
    git clone https://github.com/princepainter/ComfyUI-PainterI2Vadvanced.git && \
    cd ComfyUI-PainterI2Vadvanced && \
    if [ -f requirements.txt ]; then pip install -r requirements.txt; fi

# ---------------------------------------------------------------------------- #
# 3. DOWNLOAD MODELS
# ---------------------------------------------------------------------------- #

# --- VAE ---
RUN comfy model download \
    --url https://huggingface.co/Comfy-Org/Wan_2.2_ComfyUI_Repackaged/resolve/main/split_files/vae/wan_2.1_vae.safetensors \
    --relative-path models/vae \
    --filename wan_2.1_vae.safetensors

# --- CLIP / Text Encoder (UMT5-XXL) ---
# TODO: Replace with the correct URL for your nsfw_wan_umt5-xxl_bf16_fixed.safetensors
RUN comfy model download \
    --url https://huggingface.co/YOUR_REPO/resolve/main/nsfw_wan_umt5-xxl_bf16_fixed.safetensors \
    --relative-path models/text_encoders \
    --filename nsfw_wan_umt5-xxl_bf16_fixed.safetensors

# --- Diffusion Models (High & Low Lighting) ---
# TODO: Replace with the correct URLs for your WAN 14B NSFW models
RUN comfy model download \
    --url https://huggingface.co/YOUR_REPO/resolve/main/Wan2.2_Remix_NSFW_i2v_14b_high_lighting_fp8_e4m3fn_v2.1.safetensors \
    --relative-path models/diffusion_models \
    --filename Wan2.2_Remix_NSFW_i2v_14b_high_lighting_fp8_e4m3fn_v2.1.safetensors

RUN comfy model download \
    --url https://huggingface.co/YOUR_REPO/resolve/main/Wan2.2_Remix_NSFW_i2v_14b_low_lighting_fp8_e4m3fn_v2.1.safetensors \
    --relative-path models/diffusion_models \
    --filename Wan2.2_Remix_NSFW_i2v_14b_low_lighting_fp8_e4m3fn_v2.1.safetensors

# --- LoRAs (DR34ML4Y NSFW - High & Low) ---
# TODO: Replace with the correct URLs
RUN mkdir -p /comfyui/models/loras/wan_loras/NSFW

RUN comfy model download \
    --url https://huggingface.co/YOUR_REPO/resolve/main/DR34ML4Y_I2V_14B_HIGH_V2.safetensors \
    --relative-path models/loras/wan_loras/NSFW \
    --filename DR34ML4Y_I2V_14B_HIGH_V2.safetensors

RUN comfy model download \
    --url https://huggingface.co/YOUR_REPO/resolve/main/DR34ML4Y_I2V_14B_LOW_V2.safetensors \
    --relative-path models/loras/wan_loras/NSFW \
    --filename DR34ML4Y_I2V_14B_LOW_V2.safetensors

# --- LoRAs (LightX2V 4-Step Acceleration - High & Low Noise) ---
# TODO: Replace with the correct URLs
RUN comfy model download \
    --url https://huggingface.co/YOUR_REPO/resolve/main/wan2.2_i2v_lightx2v_4steps_lora_v1_high_noise.safetensors \
    --relative-path models/loras/wan_loras \
    --filename wan2.2_i2v_lightx2v_4steps_lora_v1_high_noise.safetensors

RUN comfy model download \
    --url https://huggingface.co/YOUR_REPO/resolve/main/wan2.2_i2v_lightx2v_4steps_lora_v1_low_noise.safetensors \
    --relative-path models/loras/wan_loras \
    --filename wan2.2_i2v_lightx2v_4steps_lora_v1_low_noise.safetensors

# ---------------------------------------------------------------------------- #
# 4. SERVERLESS SETUP
# ---------------------------------------------------------------------------- #
RUN pip install requests runpod

# Copy handler and workflow to root
COPY workflow_api.json /workflow_api.json
COPY rp_handler.py /rp_handler.py

# Start ComfyUI, then run the RunPod handler
CMD ["/bin/bash", "-c", "cd /comfyui && python main.py --listen 0.0.0.0 --port 8188 & python /rp_handler.py"]
