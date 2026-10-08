FROM python:3.13-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
ENV PYTHONPATH=/app/app NOTIZEN_ORDNER=/notizen HOST=0.0.0.0 PORT=8099
VOLUME /notizen
EXPOSE 8099
CMD ["python", "-m", "uvicorn", "main:app", "--app-dir", "app", "--host", "0.0.0.0", "--port", "8099"]
