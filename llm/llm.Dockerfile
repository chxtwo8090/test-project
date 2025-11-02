FROM python:3.11-slim

# 필요한 시스템 의존성 설치 (llama-cpp-python 빌드를 위해 필요)
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 작업 디렉토리 설정
WORKDIR /app

# LLM 서버에 필요한 Python 라이브러리 설치
COPY llm_requirements.txt .
RUN pip install --no-cache-dir -r llm_requirements.txt

# LLM API Python 코드 복사
COPY llm_api.py .

# 80번 포트로 앱을 실행
EXPOSE 80

# Uvicorn으로 FastAPI 앱 실행
CMD ["uvicorn", "llm_api:app", "--host", "0.0.0.0", "--port", "80"]