import os
import pymysql
import bcrypt
import jwt
import time
from datetime import datetime, timedelta
from functools import wraps # ⬅️ 데코레이터 구현을 위해 추가
from flask import Flask, request, jsonify
from flask_cors import CORS

# =======================================================
# 1. Flask 애플리케이션 초기 설정
# =======================================================
app = Flask(__name__)

# 💡 CORS 설정: S3 웹사이트 주소만 허용하여 보안 강화
# http://chxtwo-git.s3-website.ap-northeast-2.amazonaws.com 주소로만 API 호출 허용
CORS(app, resources={r"/*": {"origins": "http://chxtwo-git.s3-website.ap-northeast-2.amazonaws.com"}})

 # JWT 토큰 생성을 위한 비밀 키 (배포 환경에서 반드시 환경 변수로 설정되어야 합니다.)
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
            cursorclass=pymysql.cursors.DictCursor
        )
        return conn
    except Exception as e:
        print(f"Database connection error: {e}")
        return None

# =======================================================
# 4. JWT 인증 데코레이터 (추가됨)
# =======================================================
def token_required(f):
    """API 요청 헤더에서 JWT 토큰을 추출하고 유효성을 검사하는 데코레이터"""
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        if 'Authorization' in request.headers:
            auth_header = request.headers['Authorization']
            try:
                # 'Bearer ' 부분 제거
                token = auth_header.split(" ")[1] 
            except IndexError:
                return jsonify({'message': '토큰 형식이 올바르지 않습니다.'}), 401

        if not token:
            return jsonify({'message': '로그인이 필요합니다. (토큰이 누락되었습니다.)'}), 401

        try:
            # 2. 토큰 디코딩 및 유효성 검사
            data = jwt.decode(token, SECRET_KEY, algorithms=['HS256'])
            
            # 3. 디코딩된 사용자 정보를 request 객체에 저장하여 다음 함수로 전달
            request.user_id = data.get('user_id')
            request.nickname = data.get('nickname')

        except jwt.ExpiredSignatureError:
            return jsonify({'message': '토큰이 만료되었습니다. 다시 로그인해주세요.'}), 401
        except jwt.InvalidTokenError:
            return jsonify({'message': '유효하지 않은 토큰입니다.'}), 401
        except Exception as e:
            print(f"Token decoding error: {e}")
            return jsonify({'message': '인증 오류가 발생했습니다.'}), 401

        # 인증이 성공하면 원래 함수 실행
        return f(*args, **kwargs)
    return decorated


# =======================================================
# 5. 기본 엔드포인트 (ALB 연결 테스트용)
# =======================================================
@app.route('/', methods=['GET'])
def home():
    return jsonify({"message": "Flask Backend is running! (v2.0)"})


# =======================================================
# 6. 회원가입 API (/register)
# =======================================================
@app.route('/register', methods=['POST'])
def register_user():
    """회원가입 요청을 처리하고 사용자 정보를 DB에 저장합니다."""
    data = request.get_json()
    username = data.get('username')
    nickname = data.get('nickname')
    password = data.get('password')
 
    if not all([username, nickname, password]):
        return jsonify({"message": "아이디, 닉네임, 비밀번호를 모두 입력해주세요."}), 400

    conn = get_db_connection()
    if conn is None:
        return jsonify({"message": "데이터베이스 연결에 실패했습니다. (환경 변수/접속 확인)"}), 500
     
    try:
        
        hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
 
        with conn.cursor() as cursor:
            # 1. 아이디 중복 체크
            cursor.execute("SELECT user_id FROM users WHERE username = %s", (username,))
            if cursor.fetchone():
                return jsonify({"message": "이미 사용 중인 아이디입니다."}), 409
            
            # 2. DB에 사용자 정보 삽입
            SQL = "INSERT INTO users (username, nickname, password_hash) VALUES (%s, %s, %s)"
            cursor.execute(SQL, (username, nickname, hashed_password))

        conn.commit()
        return jsonify({"message": "회원가입에 성공했습니다. 로그인 페이지로 이동합니다."}), 201

    except Exception as e:
        print(f"회원가입 중 DB 오류 발생: {e}") 
        return jsonify({"message": "회원가입 중 서버 오류가 발생했습니다."}), 500
    finally:
        if conn:
            conn.close()


# =======================================================
# 7. 로그인 API (/login)
# =======================================================
@app.route('/login', methods=['POST'])
def login_user():
    """로그인 요청을 처리하고, 인증 성공 시 JWT 토큰을 발급합니다."""
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')

    if not all([username, password]):
        return jsonify({"message": "아이디와 비밀번호를 입력해주세요."}), 400

    conn = get_db_connection()
    if conn is None:
        return jsonify({"message": "데이터베이스 연결에 실패했습니다."}), 500

    try:
        with conn.cursor() as cursor:
            # 1. DB에서 사용자 정보 조회
            cursor.execute("SELECT user_id, nickname, password_hash FROM users WHERE username = %s", (username,))
            user = cursor.fetchone()

            if not user:
                 return jsonify({"message": "아이디 또는 비밀번호를 잘못 입력했습니다."}), 401

             # 2. 비밀번호 일치 확인 (bcrypt 해시 비교)
            if not bcrypt.checkpw(password.encode('utf-8'), user['password_hash'].encode('utf-8')):
                return jsonify({"message": "아이디 또는 비밀번호를 잘못 입력했습니다."}), 401

             # 3. 인증 성공: JWT 토큰 생성
            payload = {
                'user_id': user['user_id'],
                'nickname': user['nickname'],
                'exp': datetime.utcnow() + timedelta(hours=24) # 24시간 후 만료
             }
            token = jwt.encode(payload, SECRET_KEY, algorithm='HS256')

            # 4. 클라이언트에 토큰 및 사용자 정보 반환
            return jsonify({
                "message": "로그인 성공",
                "token": token,
                "user_id": user['user_id'],
                "nickname": user['nickname']
            }), 200

    except Exception as e:
        print(f"로그인 중 서버 오류 발생: {e}")
        return jsonify({"message": "로그인 중 서버 오류가 발생했습니다."}), 500
    finally:
        if conn:
            conn.close()


# =======================================================
# 8. [신규] 게시글 API (CRUD)
# =======================================================

@app.route('/posts', methods=['GET'])
def list_posts():
    """모든 게시글 목록을 최신순으로 조회합니다."""
    conn = get_db_connection()
    if conn is None:
        return jsonify({"message": "데이터베이스 연결에 실패했습니다."}), 500

    try:
        with conn.cursor() as cursor:
            # users 테이블과 JOIN하여 작성자 닉네임을 가져옵니다.
            SQL = """
            SELECT 
                p.post_id, p.title, p.content, p.views, 
                p.created_at, p.updated_at, 
                u.nickname, u.user_id
            FROM posts p
            JOIN users u ON p.user_id = u.user_id
            ORDER BY p.post_id DESC
            """
            cursor.execute(SQL)
            posts = cursor.fetchall()
        
        # 날짜 포맷팅을 위한 처리
        for post in posts:
            post['created_at'] = post['created_at'].strftime('%Y-%m-%d %H:%M')
            post['updated_at'] = post['updated_at'].strftime('%Y-%m-%d %H:%M')
            # 상세 조회 시 필요한 내용이므로 목록에서는 content를 제거합니다.
            del post['content']
            
        return jsonify(posts), 200

    except Exception as e:
        print(f"게시글 목록 조회 중 서버 오류 발생: {e}")
        return jsonify({"message": "게시글 목록 조회 중 서버 오류가 발생했습니다."}), 500
    finally:
        if conn:
            conn.close()


@app.route('/posts', methods=['POST'])
@token_required # ⬅️ JWT 인증 데코레이터 적용
def create_post():
    """새 게시글을 작성합니다. (로그인 필수)"""
    data = request.get_json()
    title = data.get('title')
    content = data.get('content')
    
    # request 객체에 저장된 user_id와 nickname을 사용 (데코레이터가 확인해 줌)
    user_id = request.user_id 
    
    if not all([title, content]):
        return jsonify({"message": "제목과 내용을 모두 입력해주세요."}), 400

    conn = get_db_connection()
    if conn is None:
        return jsonify({"message": "데이터베이스 연결에 실패했습니다."}), 500

    try:
        with conn.cursor() as cursor:
            SQL = "INSERT INTO posts (user_id, title, content) VALUES (%s, %s, %s)"
            cursor.execute(SQL, (user_id, title, content))

        conn.commit()
        return jsonify({"message": "게시글이 성공적으로 작성되었습니다."}), 201

    except Exception as e:
        print(f"게시글 작성 중 서버 오류 발생: {e}")
        return jsonify({"message": "게시글 작성 중 서버 오류가 발생했습니다."}), 500
    finally:
        if conn:
            conn.close()


# =======================================================
# 9. Gunicorn 또는 로컬 테스트용 실행
# =======================================================
if __name__ == '__main__':
     app.run(host='0.0.0.0', port=80, debug=True)