FROM python:3.11-slim

# 2. Fix OS Vulnerabilities (Fixes OpenSSL, OpenSSH, libtiff, etc.)
# This runs the updates Trivy flagged as "fixed in version X"
RUN apt-get update && apt-get upgrade -y && \
    apt-get install -y --no-install-recommends \
    # Add any system-level dependencies your app needs here
    && apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# 3. Set a secure working directory
WORKDIR /app

# 4. Patch Python Tools (Fixes wheel and jaraco.context issues)
# We upgrade pip/wheel/setuptools before installing requirements
RUN pip install --no-cache-dir --upgrade pip wheel setuptools jaraco.context

# 5. Install application dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 6. Copy application code
COPY . .

# 7. Security Hardening: Run as a non-root user
# This is a core "Hardening" requirement in your challenge
RUN useradd -m team4user
USER team4user

# 8. Expose and Start
EXPOSE 5000
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--timeout", "600", "app:app"]