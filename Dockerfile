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
# 3. NETWORK VOLUME — models are pre-loaded on the RunPod Network Volume.
#    extra_model_paths.yaml tells ComfyUI to look at /runpod-volume for all
#    diffusion models, text encoders, VAE, and LoRAs at runtime.
# ---------------------------------------------------------------------------- #
COPY extra_model_paths.yaml /comfyui/extra_model_paths.yaml

# ---------------------------------------------------------------------------- #
# 4. SERVERLESS SETUP
# ---------------------------------------------------------------------------- #
RUN pip install requests runpod

# Copy handler and workflow to root
COPY workflow_api.json /workflow_api.json
COPY rp_handler.py /rp_handler.py

# Start ComfyUI, then run the RunPod handler
CMD ["/bin/bash", "-c", "cd /comfyui && python main.py --listen 0.0.0.0 --port 8188 & python /rp_handler.py"]
