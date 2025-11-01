# 1. 기본 이미지: Python 3.9 사용
FROM python:3.9-slim

# 2. 작업 디렉터리 설정
WORKDIR /app

# 3. requirements.txt 복사 및 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 4. 앱 코드 전체 복사
COPY . .

# 5. Gunicorn으로 앱 실행 (포트 8000)
#    (Nginx는 나중에 Kubernetes Ingress가 대체합니다)
CMD ["gunicorn", "-b", "0.0.0.0:8000", "app:app"]