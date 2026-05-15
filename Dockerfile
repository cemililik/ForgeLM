# ==============================================================================
# ForgeLM Docker Image
# Multi-stage build for minimal image size with CUDA support.
#
# Usage:
#   Build:
#     docker build -t forgelm .
#     docker build -t forgelm:eval --build-arg INSTALL_EVAL=true .
#     docker build -t forgelm:full --build-arg INSTALL_EVAL=true --build-arg INSTALL_UNSLOTH=true .
#
#   Run:
#     docker run --gpus all -v $(pwd)/my_config.yaml:/workspace/config.yaml \
#       -v $(pwd)/data:/workspace/data \
#       -v $(pwd)/output:/workspace/output \
#       forgelm --config /workspace/config.yaml
#
#   Dry-run:
#     docker run forgelm --config /workspace/config.yaml --dry-run
#
#   Benchmark only:
#     docker run --gpus all -v $(pwd)/model:/workspace/model \
#       forgelm:eval --config /workspace/config.yaml --benchmark-only /workspace/model
# ==============================================================================

# --- Stage 1: Base with CUDA ---
FROM nvidia/cuda:12.4.1-devel-ubuntu22.04 AS base

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.11 \
    python3.11-venv \
    python3-pip \
    git \
    && rm -rf /var/lib/apt/lists/* \
    && update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 1

WORKDIR /app

# --- Stage 2: Install dependencies ---
FROM base AS deps

# Copy only dependency files first (cache layer)
COPY pyproject.toml README.md ./
COPY forgelm/__init__.py forgelm/__init__.py

# Install core + QLoRA (bitsandbytes included by default on Linux)
ARG INSTALL_QLORA=true
RUN python3 -m pip install --no-cache-dir -e . && \
    if [ "$INSTALL_QLORA" = "true" ]; then \
    python3 -m pip install --no-cache-dir -e ".[qlora]"; \
    fi

# Optional: evaluation harness
ARG INSTALL_EVAL=false
RUN if [ "$INSTALL_EVAL" = "true" ]; then \
    python3 -m pip install --no-cache-dir -e ".[eval]"; \
    fi

# Optional: Unsloth backend
ARG INSTALL_UNSLOTH=false
RUN if [ "$INSTALL_UNSLOTH" = "true" ]; then \
    python3 -m pip install --no-cache-dir -e ".[unsloth]"; \
    fi

# --- Stage 3: Final runtime image ---
FROM deps AS runtime

# Copy source. `.dockerignore` excludes tests/, notebooks/, docs/, .git/,
# build artefacts, and AI-agent working directories so the runtime image
# stays minimal and free of non-production material (SonarCloud S6470).
COPY . .

# Install with full source (non-editable for production)
RUN python3 -m pip install --no-cache-dir .

# Drop to a non-root user for the runtime stage so the container does not
# execute training workloads as UID 0 (SonarCloud S6471). The `/workspace`
# mount point is owned by the forgelm user so bind-mounted configs and
# output directories remain writable.
RUN groupadd --system --gid 1000 forgelm \
    && useradd --system --uid 1000 --gid forgelm --create-home --home-dir /home/forgelm forgelm \
    && mkdir -p /workspace \
    && chown -R forgelm:forgelm /workspace /home/forgelm

USER forgelm

# Default working directory for user configs/data
WORKDIR /workspace

# Verify installation
RUN forgelm --version

ENTRYPOINT ["forgelm"]
CMD ["--help"]
