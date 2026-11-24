FROM python:3.13-slim
WORKDIR /app
COPY app.py patient.py index.html ./
RUN mkdir /data && chown 10001:10001 /data
USER 10001:10001
ENV HOST=0.0.0.0 PORT=8080 TRAINING_DB=/data/training.sqlite3
EXPOSE 8080
CMD ["python", "app.py"]
