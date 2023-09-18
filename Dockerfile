# Use an official Python runtime as the base image
FROM --platform=linux/amd64 python:3.10-slim

# Set the working directory in the container
WORKDIR /code

# Copy the current directory contents into the container at /code/
COPY . /code/.

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir --upgrade -r /code/env/requirements.txt

# Expose the port your app runs on
EXPOSE 8080

# Start the Python app and ngrok with the specified domain
CMD uvicorn main:app --host 0.0.0.0 --port 8080
