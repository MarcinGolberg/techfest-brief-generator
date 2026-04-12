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

# 6. Copy ONLY the necessary application code WITH strict ownership
# This maps exactly to your project tree to avoid copying .git, tests, or uploads
COPY --chown=root:root --chmod=0555 services/ ./services/
COPY --chown=root:root --chmod=0555 static/ ./static/
COPY --chown=root:root --chmod=0555 templates/ ./templates/
COPY --chown=root:root --chmod=0555 prompts/ ./prompts/
COPY --chown=root:root --chmod=0555 images/ ./images/
COPY --chown=root:root --chmod=0555 app.py file_parser.py ./

# 6.5 Create dynamic directories and grant write access to the runtime user
# This allows the app to save uploads and generated files without giving it
# permission to modify the source code.
RUN mkdir -p /app/generated /app/uploads && \
    chown -R team4user:team4user /app/generated /app/uploads && \
    chmod -R 0755 /app/generated /app/uploads

# 7. Container Health Monitoring
# Scanners require this to ensure the orchestrator can monitor app health
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8080/ || exit 1

# 8. Switch to the non-root user
USER team4user

# 9. Expose and Start
EXPOSE 8080
# Make sure app.py defines a Flask/FastAPI instance named 'app'
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--timeout", "600", "app:app"]