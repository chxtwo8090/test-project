# 1. Python 3.10 버전을 기반으로 시작
FROM python:3.10-slim

# 2. 작업 디렉토리 설정
WORKDIR /app

# 3. requirements.txt 복사 및 설치
# (Flask, Gunicorn, PyMySQL 등 프로젝트에 필요한 라이브러리)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 4. 프로젝트의 모든 소스코드 복사
COPY . .

# 5. [중요] 80번 포트로 앱을 실행
EXPOSE 80

# 6. Gunicorn으로 Flask 앱 실행 (CORS 헤더 강제 삽입)
CMD ["gunicorn", \
     "--bind", "0.0.0.0:80", \
     "--header", "Access-Control-Allow-Origin: *", \
     "--header", "Access-Control-Allow-Credentials: true", \
     "app:app"]