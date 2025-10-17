# Use Python 3.10 slim image
FROM python:3.10-slim

# Set working directory
WORKDIR /app

# Copy dependencies first for caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy all project files
COPY . .

# Expose HF Space default port
EXPOSE 7860

# Command to run FastAPI
CMD ["uvicorn", "Student.app:app", "--host", "0.0.0.0", "--port", "7860"]
