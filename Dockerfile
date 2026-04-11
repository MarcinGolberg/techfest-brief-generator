# Use a lightweight Python image
FROM python:3.11

# Set the working directory
WORKDIR /app

# Copy and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY . .

# Expose the port Flask runs on (default 5000)
EXPOSE 5000

# Run the application using Gunicorn (recommended for production)
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "app:app"]