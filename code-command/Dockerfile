# Code Command - Python Sandbox Image
# Build: docker build -t code-sandbox:latest .

FROM python:3.11-slim

# Environment variables to prevent sandbox errors
ENV MPLCONFIGDIR=/workspace
ENV MPLBACKEND=Agg
ENV XDG_CACHE_HOME=/workspace/.cache
ENV OPENBLAS_NUM_THREADS=1
ENV OMP_NUM_THREADS=1
ENV PYTHONUNBUFFERED=1

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    graphviz \
    fonts-dejavu \
    fonts-liberation \
    fontconfig \
    && rm -rf /var/lib/apt/lists/* \
    && fc-cache -f

# Install Python packages for data science and document generation
RUN pip install --no-cache-dir \
    numpy \
    pandas \
    matplotlib \
    seaborn \
    scipy \
    scikit-learn \
    openpyxl \
    xlrd \
    requests \
    beautifulsoup4 \
    lxml \
    pillow \
    sympy \
    python-pptx \
    graphviz

# Create /mnt/data symlink for LibreChat compatibility
# LibreChat code interpreter expects files at /mnt/data/
RUN mkdir -p /mnt && ln -s /workspace /mnt/data

# Create non-root user for extra security
RUN useradd -m -s /bin/bash sandbox
USER sandbox

WORKDIR /workspace
