FROM python:3.11-slim-bookworm

# 1. Install basics (no GPG needed here)
RUN apt-get update && apt-get install -y curl ca-certificates perl ghostscript git pandoc

# 2. Add MiKTeX repo with [trusted=yes] to skip GPG verification
RUN echo "deb [trusted=yes] https://miktex.org/download/debian bookworm universe" \
    > /etc/apt/sources.list.d/miktex.list

# 3. Install MiKTeX (adding --allow-unauthenticated as a backup)
RUN apt-get update && \
    apt-get install -y --allow-unauthenticated miktex

# 4. Finish Setup
RUN miktexsetup finish && \
    initexmf --admin --set-config-value [MPM]AutoInstall=1

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 5. Copy App Code
COPY . .

# Run the application with gunicorn
CMD gunicorn --bind 0.0.0.0:${PORT:-5000}  flaskapp:app