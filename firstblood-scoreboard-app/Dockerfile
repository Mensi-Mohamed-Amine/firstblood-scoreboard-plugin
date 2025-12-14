FROM python:3.11-slim

# Install dependencies
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy code
COPY server.py .
COPY templates/ templates/
COPY static/ static/

# Expose port
EXPOSE 5000

# Run with eventlet for Socket.IO
CMD ["python", "server.py"]
