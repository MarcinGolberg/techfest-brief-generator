FROM python:3.11-slim

# 1. Security Hardening: Create the non-root user FIRST
RUN useradd -m team4user

# 2. Fix OS Vulnerabilities and install 'curl' for the Healthcheck
RUN apt-get update && apt-get upgrade -y && \
    apt-get install -y --no-install-recommends \
    curl \
    && apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# 3. Set a secure working directory
WORKDIR /app

# 4. Patch Python Tools
RUN pip install --no-cache-dir --upgrade pip wheel setuptools jaraco.context

# 5. Install application dependencies
# We do this as root so they are installed globally in the container
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 6. Copy application code WITH strict ownership
# This tells scanners that root does not own the app files
COPY --chown=team4user:team4user --chmod=0555 . .

# 7. Container Health Monitoring
# Scanners require this to ensure the orchestrator can monitor app health
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8080/ || exit 1

# 8. Switch to the non-root user
USER team4user

# 9. Expose and Start
EXPOSE 8080
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--timeout", "600", "app:app"]