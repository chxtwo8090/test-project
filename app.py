import os
import pymysql
import bcrypt
import jwt
from datetime import datetime, timedelta
from functools import wraps
from flask import Flask, request, jsonify
from flask_cors import CORS

# =======================================================
# 1. Flask 애플리케이션 초기 설정
# =======================================================
app = Flask(__name__)

# 💡 CORS 설정: S3 웹사이트 주소만 허용 (Node.js app.js의 설정과 동일)
# Node.js app.js의 origin: 'http://project-chxtwo.s3-website.ap-northeast-2.amazonaws.com'
# 사용자님의 실제 S3 주소: http://chxtwo-git.s3-website.ap-northeast-2.amazonaws.com
CORS(app, resources={r"/*": {"origins": "http://chxtwo-git.s3-website.ap-northeast-2.amazonaws.com"}})

# JWT 토큰 생성을 위한 비밀 키 (Node.js의 JWT_SECRET과 동일한 역할)
# 실제 배포 시에는 GitHub Secrets에 등록해야 합니다.
SECRET_KEY = os.environ.get("SECRET_KEY", "your_strong_secret_key_that_should_be_in_secrets")


# =======================================================
# 2. RDS 환경 변수 로드 및 3. DB 연결 함수
# =======================================================
DB_HOST = os.environ.get("DB_HOST")
DB_NAME = os.environ.get("DB_NAME")
DB_USER = os.environ.get("DB_USER")
DB_PASSWORD = os.environ.get("DB_PASSWORD")

def get_db_connection():
    """RDS MySQL 연결을 생성하고 반환합니다."""
    if not all([DB_HOST, DB_NAME, DB_USER, DB_PASSWORD]):
        print("Error: DB environment variables are not set.")
        return None
        
    try:
        conn = pymysql.connect(
            host=DB_HOST, user=DB_USER, password=DB_PASSWORD, database=DB_NAME,
            charset='utf8mb4', cursorclass=pymysql.cursors.DictCursor
        )
        return conn
    except Exception as e:
        print(f"Database connection error: {e}")
        return None

# =======================================================
# 4. JWT 인증 데코레이터
# (Node.js app.js의 JWT 미들웨어와 동일한 역할)
# =======================================================
def token_required(f):
    """API 요청 헤더에서 JWT 토큰을 추출하고 유효성을 검사하는 데코레이터"""
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        if 'Authorization' in request.headers:
            auth_header = request.headers['Authorization']
            try:
                token = auth_header.split(" ")[1] 
            except IndexError:
                return jsonify({'message': '토큰 형식이 올바르지 않습니다.'}), 401
        if not token:
            return jsonify({'message': '로그인이 필요합니다. (토큰이 누락되었습니다.)'}), 401
        try:
            data = jwt.decode(token, SECRET_KEY, algorithms=['HS256'])
            # 사용자 정보를 request 객체에 저장
            request.user_id = data.get('user_id')
            request.nickname = data.get('nickname')
        except jwt.ExpiredSignatureError:
            return jsonify({'message': '토큰이 만료되었습니다. 다시 로그인해주세요.'}), 401
        except jwt.InvalidTokenError:
            return jsonify({'message': '유효하지 않은 토큰입니다.'}), 401
        except Exception as e:
            print(f"Token decoding error: {e}")
            return jsonify({'message': '인증 오류가 발생했습니다.'}), 401
        return f(*args, **kwargs)
    return decorated


# =======================================================
# 5. 기본 엔드포인트
# =======================================================
@app.route('/', methods=['GET'])
def home():
    return jsonify({"message": "Flask Backend is running! (v3.0 - Node.js feature parity)"})


# =======================================================
# 6. 회원가입 API (/register) - Node.js 로직 이식 완료
# =======================================================
@app.route('/register', methods=['POST'])
def register_user():
    data = request.get_json()
    username = data.get('username')
    nickname = data.get('nickname')
    password = data.get('password')

    if not all([username, nickname, password]):
        # Node.js 오류 메시지와 최대한 유사하게 반환
        return jsonify({"message": "아이디, 비밀번호, 닉네임을 모두 입력해주세요."}), 400

    conn = get_db_connection()
    if conn is None:
        return jsonify({"message": "데이터베이스 연결에 실패했습니다."}), 500
    
    try:
        # Node.js의 bcrypt.hash(password, 10)과 동일한 역할
        hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt(10)).decode('utf-8')

        with conn.cursor() as cursor:
            # 중복 체크
            cursor.execute("SELECT user_id FROM users WHERE username = %s", (username,))
            if cursor.fetchone():
                return jsonify({"message": "이미 존재하는 아이디입니다."}), 409
            
            # DB 삽입 (Node.js의 NOW() 대신 MySQL 함수 사용)
            SQL = "INSERT INTO users (username, nickname, password_hash, created_at) VALUES (%s, %s, %s, NOW())"
            cursor.execute(SQL, (username, nickname, hashed_password))

        conn.commit()
        # Node.js와 동일한 응답
        return jsonify({"message": "회원가입이 성공적으로 완료되었습니다."}), 201

    except Exception as e:
        print(f"회원가입 중 DB 오류 발생: {e}") 
        return jsonify({"message": "회원가입 중 서버 오류가 발생했습니다."}), 500
    finally:
        if conn: conn.close()


# =======================================================
# 7. 로그인 API (/login) - Node.js 로직 이식 완료
# =======================================================
@app.route('/login', methods=['POST'])
def login_user():
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
            # 1. 사용자 정보 조회
            cursor.execute("SELECT user_id, nickname, password_hash FROM users WHERE username = %s", (username,))
            user = cursor.fetchone()

            if not user:
                # Node.js와 동일한 메시지
                return jsonify({"message": "아이디 또는 비밀번호가 일치하지 않습니다."}), 401

            # 2. 비밀번호 일치 확인 (Node.js의 bcrypt.compare와 동일)
            if not bcrypt.checkpw(password.encode('utf-8'), user['password_hash'].encode('utf-8')):
                return jsonify({"message": "아이디 또는 비밀번호가 일치하지 않습니다."}), 401

            # 3. JWT 토큰 생성 (Node.js의 jwt.sign과 동일)
            payload = {
                'user_id': user['user_id'],
                'nickname': user['nickname'],
                'exp': datetime.utcnow() + timedelta(hours=1) # Node.js와 동일하게 1시간 만료
            }
            token = jwt.encode(payload, SECRET_KEY, algorithm='HS256')

            # 4. Node.js와 동일한 응답 형식
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
        if conn: conn.close()


# =======================================================
# 8. 게시글 API (CRUD) - Node.js 로직 이식 완료
# =======================================================

# 목록 조회 (GET /posts) - Node.js와 동일하게 검색 기능 지원
@app.route('/posts', methods=['GET'])
def list_posts():
    conn = get_db_connection()
    if conn is None: return jsonify({"message": "DB 연결 실패"}), 500
    try:
        search_query = request.args.get('search', '')
        
        SQL = """
            SELECT 
                p.post_id, p.title, p.content, p.views, 
                p.created_at, p.updated_at, 
                u.nickname AS authorName, u.user_id
            FROM posts p
            JOIN users u ON p.user_id = u.user_id
        """
        params = []
        
        # Node.js와 동일하게 제목 또는 내용으로 검색
        if search_query:
            SQL += " WHERE p.title LIKE %s OR p.content LIKE %s"
            params.append(f"%{search_query}%")
            params.append(f"%{search_query}%")
            
        SQL += " ORDER BY p.post_id DESC"
        
        with conn.cursor() as cursor:
            cursor.execute(SQL, params)
            posts = cursor.fetchall()
        
        # Node.js는 날짜를 문자열로 반환하므로 Flask에서도 포맷팅
        for post in posts:
            if post.get('created_at'): post['created_at'] = post['created_at'].strftime('%Y-%m-%dT%H:%M:%S.000Z')
            if post.get('updated_at'): post['updated_at'] = post['updated_at'].strftime('%Y-%m-%dT%H:%M:%S.000Z')
            # Node.js API는 목록에서 content를 제거하지 않으므로 유지합니다.

        return jsonify(posts), 200

    except Exception as e:
        print(f"게시글 목록 조회 중 서버 오류 발생: {e}")
        return jsonify({"error": "게시글 목록을 불러오는 데 실패했습니다."}), 500
    finally:
        if conn: conn.close()


# 게시글 작성 (POST /posts) - JWT 인증 필요
@app.route('/posts', methods=['POST'])
@token_required 
def create_post():
    data = request.get_json()
    title = data.get('title')
    content = data.get('content')
    
    # Node.js 프론트엔드 코드가 authorId를 body에 담아 보냅니다.
    # Flask에서는 토큰에서 user_id를 가져오므로, body의 authorId를 무시합니다.
    user_id = request.user_id 
    
    if not all([title, content]):
        return jsonify({"error": "제목과 내용이 필요합니다."}), 400

    conn = get_db_connection()
    if conn is None: return jsonify({"error": "DB 연결 실패"}), 500

    try:
        with conn.cursor() as cursor:
            # Node.js와 동일하게 created_at에 NOW() 사용
            SQL = "INSERT INTO posts (user_id, title, content, views, created_at) VALUES (%s, %s, %s, 0, NOW())"
            cursor.execute(SQL, (user_id, title, content))

        conn.commit()
        # Node.js와 유사하게 postId 반환
        return jsonify({"message": "게시글이 성공적으로 작성되었습니다.", "postId": cursor.lastrowid}), 201

    except Exception as e:
        print(f"게시글 작성 중 서버 오류 발생: {e}")
        return jsonify({"error": "게시글 작성 중 서버 오류가 발생했습니다."}), 500
    finally:
        if conn: conn.close()


# =======================================================
# 9. Gunicorn 또는 로컬 테스트용 실행
# =======================================================
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=80, debug=True)