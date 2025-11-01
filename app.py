import os
import pymysql
import bcrypt # ⬅️ 추가된 비밀번호 암호화 라이브러리
import jwt      # 🚨 다음 단계인 로그인 구현을 위해 미리 추가합니다.
import time
from datetime import datetime, timedelta
from flask import Flask, request, jsonify
from flask_cors import CORS

# =======================================================
# 1. Flask 애플리케이션 초기 설정
# =======================================================
app = Flask(__name__)
# 모든 도메인에서의 접속을 허용합니다. (CORS 설정)
CORS(app) 

# JWT 토큰 생성을 위한 비밀 키 (배포 환경에서 반드시 환경 변수로 설정되어야 합니다.)
# 현재는 임시 키를 사용합니다. 실제 배포 시에는 GitHub Secrets에 등록하세요.
SECRET_KEY = os.environ.get("SECRET_KEY", "your_strong_secret_key_that_should_be_in_secrets")


# =======================================================
# 2. RDS 환경 변수 로드 (GitHub Secrets에서 주입된 값)
# =======================================================
DB_HOST = os.environ.get("DB_HOST")
DB_NAME = os.environ.get("DB_NAME")
DB_USER = os.environ.get("DB_USER")
DB_PASSWORD = os.environ.get("DB_PASSWORD")

# =======================================================
# 3. DB 연결 함수
# =======================================================
def get_db_connection():
    """RDS MySQL 연결을 생성하고 반환합니다."""
    # 환경 변수 중 하나라도 없으면 연결 시도 안 함
    if not all([DB_HOST, DB_NAME, DB_USER, DB_PASSWORD]):
        print("Error: DB environment variables are not set.")
        return None
        
    try:
        conn = pymysql.connect(
            host=DB_HOST,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME,
            charset='utf8mb4',
            cursorclass=pymysql.cursors.DictCursor # 딕셔너리 형태로 결과를 받기 위해 설정
        )
        return conn
    except Exception as e:
        # CloudWatch Logs에 오류를 출력
         print(f"Database connection error: {e}")
         return None

# =======================================================
# 4. 기본 엔드포인트 (ALB 연결 테스트용)
# =======================================================
@app.route('/', methods=['GET'])
def home():
    return jsonify({"message": "Flask Backend is running! (v1.0)"})

# =======================================================
# 5. [완성] 회원가입 API (/register)
# =======================================================
@app.route('/register', methods=['POST'])
def register_user():
    """회원가입 요청을 처리하고 사용자 정보를 DB에 저장합니다."""
    data = request.get_json()
    username = data.get('username')
    nickname = data.get('nickname')
    password = data.get('password')

    # 필수 필드 누락 체크
    if not all([username, nickname, password]):
        return jsonify({"message": "아이디, 닉네임, 비밀번호를 모두 입력해주세요."}), 400

    conn = get_db_connection()
    if conn is None:
        return jsonify({"message": "데이터베이스 연결에 실패했습니다. (환경 변수/접속 확인)"}), 500
    
    # 1. 비밀번호 해시 (암호화)
    # bcrypt는 바이트 문자열을 사용하므로, encode() 호출하여 해시 후, decode()로 문자열로 저장
    try:
        # Cost Factor는 12로 설정 (기본값)
        hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    except Exception as e:
        print(f"Bcrypt hashing error: {e}")
        return jsonify({"message": "비밀번호 암호화 중 오류가 발생했습니다."}), 500


    try:
        with conn.cursor() as cursor:
            # 2. 아이디 중복 체크
            # SQL Injection 방지를 위해 %s 사용
            cursor.execute("SELECT user_id FROM users WHERE username = %s", (username,))
            if cursor.fetchone():
                return jsonify({"message": "이미 사용 중인 아이디입니다."}), 409
            
            # 3. DB에 사용자 정보 삽입
            SQL = "INSERT INTO users (username, nickname, password_hash) VALUES (%s, %s, %s)"
            cursor.execute(SQL, (username, nickname, hashed_password))

        conn.commit()
        
        # 201 Created 응답
        return jsonify({"message": "회원가입에 성공했습니다. 로그인 페이지로 이동합니다."}), 201

    except Exception as e:
        # SQL 관련 오류 발생 시
        print(f"회원가입 중 DB 오류 발생: {e}") 
        return jsonify({"message": "회원가입 중 서버 오류가 발생했습니다."}), 500
    finally:
        # 연결은 항상 닫아줍니다.
        if conn:
            conn.close()


# =======================================================
# 6. 로그인 API (/login) - 🚨 다음 단계에서 완성할 예정입니다.
# =======================================================
@app.route('/login', methods=['POST'])
def login_user():
    # 이 부분은 다음 단계에서 완성합니다.
    return jsonify({"message": "로그인 기능은 아직 구현되지 않았습니다."}), 501


# =======================================================
# 7. Gunicorn 또는 로컬 테스트용 실행
# =======================================================
if __name__ == '__main__':
    # 로컬 테스트 시, 환경 변수를 설정해야 DB 연결이 가능합니다.
    # Ex) os.environ['DB_HOST']='127.0.0.1', ...
    app.run(host='0.0.0.0', port=80, debug=True)