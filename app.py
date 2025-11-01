import os
import pymysql
import bcrypt
from flask import Flask, request, jsonify
from flask_cors import CORS

# =======================================================
# 1. Flask 애플리케이션 초기 설정
# =======================================================
app = Flask(__name__)
# 모든 도메인에서의 접속을 허용합니다. (테스트 목적)
CORS(app) 

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
    try:
        conn = pymysql.connect(
            host=DB_HOST,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME,
            charset='utf8mb4',
            cursorclass=pymysql.cursors.DictCursor
        )
        return conn
    except Exception as e:
        # CloudWatch Logs에 오류를 출력
        print(f"Database connection error: {e}")
        # DB 연결 실패 시 에러를 반환
        return None

# =======================================================
# 4. 기본 엔드포인트 (ALB 연결 테스트용)
# =======================================================
@app.route('/')
def home():
    """ALB가 Flask 앱까지 연결되었는지 확인하는 기본 엔드포인트"""
    try:
        conn = get_db_connection()
        if conn:
            conn.close()
            return jsonify({"status": "ok", "message": "Flask 앱과 RDS 연결 확인됨!"}), 200
        else:
            return jsonify({"status": "error", "message": "Flask 앱 실행 중, RDS 연결 실패."}), 500
    except Exception as e:
        return jsonify({"status": "error", "message": f"서버 오류: {e}"}), 500


# =======================================================
# 5. [뼈대] 회원가입 API (register.html에서 사용)
# =======================================================
@app.route('/register', methods=['POST'])
def register_user():
    """회원가입 요청 처리 엔드포인트"""
    data = request.get_json()
    username = data.get('username')
    nickname = data.get('nickname')
    password = data.get('password')

    if not all([username, nickname, password]):
        return jsonify({"message": "필수 정보가 누락되었습니다."}), 400

    conn = get_db_connection()
    if conn is None:
        return jsonify({"message": "데이터베이스 연결에 실패했습니다."}), 500

    # 🚨 여기에 실제 DB INSERT 로직이 들어갑니다. (현재는 뼈대만)
    # try:
    #     with conn.cursor() as cursor:
    #         # 1. DB에 사용자 테이블이 있어야 합니다.
    #         # 2. 중복 체크 및 암호화 로직이 필요합니다.
    #         # SQL = "INSERT INTO users (username, nickname, password) VALUES (%s, %s, %s)"
    #         # cursor.execute(SQL, (username, nickname, password))
    #     conn.commit()
    #     conn.close()
    #     return jsonify({"message": "회원가입에 성공했습니다."}), 201
    # except pymysql.err.IntegrityError:
    #     conn.close()
    #     return jsonify({"message": "이미 사용 중인 아이디입니다."}), 409
    # except Exception as e:
    #     conn.close()
    #     return jsonify({"message": f"회원가입 중 서버 오류가 발생했습니다: {e}"}), 500
    
    # ⬇️ 임시 응답 (DB 연결 없이 API 뼈대만 작동 확인)
    conn.close()
    return jsonify({"message": f"회원가입 API 호출 성공 (DB 연결 필요): {username}"}), 201


if __name__ == '__main__':
    # Gunicorn이 서버를 실행하므로, 이 블록은 로컬 테스트용입니다.
    # ECS에서는 실행되지 않습니다.
    app.run(host='0.0.0.0', port=80)