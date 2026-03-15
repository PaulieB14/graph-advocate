FROM python:3.13-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir "a2a-sdk[http-server]"

COPY . .

EXPOSE 8765

CMD ["python", "a2a_server.py"]
