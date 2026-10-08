# Use the official vllm image for GPU with Volta, Turing, Ampere,
# Ada Lovelace, Hopper, and Blackwell architectures
# (7.0 <= Compute Capability <= 12.1)
#
# Default: vLLM 0.21.0 with CUDA 13.0
# For CUDA 12.9, use:
# FROM vllm/vllm-openai:v0.21.0-cu129
#
# Supports x86_64 and ARM/AArch64.

FROM vllm/vllm-openai:v0.21.0

# Install libgl for OpenCV support and Noto fonts for Chinese characters
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        fonts-noto-core \
        fonts-noto-cjk \
        fontconfig \
        libgl1 && \
    fc-cache -fv && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Install MinerU
RUN python3 -m pip install -U \
        'mineru[core]>=3.4.0' \
        --break-system-packages && \
    python3 -m pip cache purge

# Download MinerU models from Hugging Face.
#
# MinerU 4.x no longer supports:
#   mineru-models-download -m all
#
# The current model download workflow uses mineru-kit.
RUN mineru-kit models download \
    --tier standard \
    --small-backend torch \
    --vlm-engine vllm \
    -s huggingface

# Use locally downloaded models at runtime.
ENV MINERU_MODEL_SOURCE=local

# Set the entry point to activate the local model configuration
# and run the requested command.
ENTRYPOINT ["/bin/bash", "-c", "exec \"$@\"", "--"]