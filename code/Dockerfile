# Hermes Evolution — unified image
# Serves as both evo-runner (CLI, on-demand) and evo-api (FastAPI, persistent)
# docker-compose overrides CMD per service

FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    git curl && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /opt/self-evolution

# Clone and install hermes-agent-self-evolution
RUN git clone https://github.com/NousResearch/hermes-agent-self-evolution.git . && \
    pip install --no-cache-dir -e ".[dev]" && \
    pip install --no-cache-dir optuna

# Install evo-runner + evo-api deps
RUN pip install --no-cache-dir \
    click \
    fastapi \
    uvicorn[standard] \
    httpx \
    pyyaml \
    python-multipart

# Copy application code
COPY runner.py /app/runner.py
COPY evo_api/ /app/evo_api/
COPY aflow_adapter/ /app/aflow_adapter/

WORKDIR /app

# Thin bash wrapper: git pull latest self-evolution on each run
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
# Default: evo-api. Override in docker-compose for runner.
CMD ["api"]
