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

# 💡 CORS 설정: S3 웹사이트 주소만 허용
CORS(app, resources={r"/*": {"origins": "http://chxtwo-git.s3-website.ap-northeast-2.amazonaws.com"}})

# JWT 토큰 생성을 위한 비밀 키
SECRET_KEY = os.environ.get("SECRET_KEY", "your_strong_secret_key_that_should_be_in_secrets")


# =======================================================
# 2. RDS 환경 변수 로드 및 3. DB 연결 함수 (변경 없음)
# =======================================================
DB_HOST = os.environ.get("DB_HOST")
DB_NAME = os.environ.get("DB_NAME")
DB_USER = os.environ.get("DB_USER")
DB_PASSWORD = os.environ.get("DB_PASSWORD")

def get_db_connection():
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
# 4. JWT 인증 데코레이터 (변경 없음)
# =======================================================
def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        if 'Authorization' in request.headers:
            auth_header = request.headers['Authorization']
            try: token = auth_header.split(" ")[1] 
            except IndexError: return jsonify({'message': '토큰 형식이 올바르지 않습니다.'}), 401
        if not token: return jsonify({'message': '로그인이 필요합니다. (토큰이 누락되었습니다.)'}), 401
        try:
            data = jwt.decode(token, SECRET_KEY, algorithms=['HS256'])
            request.user_id = data.get('user_id')
            request.nickname = data.get('nickname')
        except jwt.ExpiredSignatureError: return jsonify({'message': '토큰이 만료되었습니다.'}), 401
        except jwt.InvalidTokenError: return jsonify({'message': '유효하지 않은 토큰입니다.'}), 401
        except Exception as e: return jsonify({'message': '인증 오류가 발생했습니다.'}), 401
        return f(*args, **kwargs)
    return decorated

# =======================================================
# 5. 기본 엔드포인트 (ALB Health Check용)
# =======================================================
@app.route('/', methods=['GET'])
def home():
    return "OK", 200 # ALB가 Healthy로 인식하도록 수정

# =======================================================
# 6. 회원가입 API (/register) (변경 없음)
# =======================================================
@app.route('/register', methods=['POST'])
def register_user():
    data = request.get_json()
    username = data.get('username')
    nickname = data.get('nickname')
    password = data.get('password')
    if not all([username, nickname, password]):
        return jsonify({"message": "아이디,  비밀번호, 닉네임을 모두 입력하세요."}), 400
    conn = get_db_connection()
    if conn is None: return jsonify({"message": "DB 연결 실패"}), 500
    try:
        hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt(10)).decode('utf-8')
        with conn.cursor() as cursor:
            cursor.execute("SELECT user_id FROM users WHERE username = %s", (username,))
            if cursor.fetchone():
                return jsonify({"message": "이미 존재하는 아이디입니다."}), 409
            SQL = "INSERT INTO users (username, nickname, password_hash, created_at) VALUES (%s, %s, %s, NOW())"
            cursor.execute(SQL, (username, nickname, hashed_password))
        conn.commit()
        return jsonify({"message": "회원가입이 성공적으로 완료되었습니다."}), 201
    except Exception as e:
        print(f"회원가입 중 DB 오류 발생: {e}") 
        return jsonify({"message": "회원가입 중 서버 오류가 발생했습니다."}), 500
    finally:
        if conn: conn.close()

# =======================================================
# 7. 로그인 API (/login) (변경 없음)
# =======================================================
@app.route('/login', methods=['POST'])
def login_user():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    if not all([username, password]): return jsonify({"message": "아이디와 비밀번호를 입력해주세요."}), 400
    conn = get_db_connection()
    if conn is None: return jsonify({"message": "DB 연결 실패"}), 500
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT user_id, nickname, password_hash FROM users WHERE username = %s", (username,))
            user = cursor.fetchone()
            if not user: return jsonify({"message": "아이디 또는 비밀번호가 일치하지 않습니다."}), 401
            if not bcrypt.checkpw(password.encode('utf-8'), user['password_hash'].encode('utf-8')):
                return jsonify({"message": "아이디 또는 비밀번호가 일치하지 않습니다."}), 401
            payload = {'user_id': user['user_id'], 'nickname': user['nickname'], 'exp': datetime.utcnow() + timedelta(hours=1)}
            token = jwt.encode(payload, SECRET_KEY, algorithm='HS256')
            return jsonify({"message": "로그인 성공", "token": token, "user_id": user['user_id'], "nickname": user['nickname']}), 200
    except Exception as e:
        print(f"로그인 중 서버 오류 발생: {e}")
        return jsonify({"message": "로그인 중 서버 오류가 발생했습니다."}), 500
    finally:
        if conn: conn.close()

# =======================================================
# 8. 게시글 API (CRUD)
# =======================================================

# 목록 조회 (GET /posts) - 검색 기능 포함
@app.route('/posts', methods=['GET'])
def list_posts():
    conn = get_db_connection()
    if conn is None: return jsonify({"error": "DB 연결 실패"}), 500
    try:
        search_query = request.args.get('search', '')
        SQL = """
            SELECT p.post_id, p.title, p.views, p.created_at, u.nickname AS authorName, u.user_id
            FROM posts p
            LEFT JOIN users u ON p.user_id = u.user_id
        """
        params = []
        if search_query:
            SQL += " WHERE p.title LIKE %s OR p.content LIKE %s"
            params.extend([f"%{search_query}%", f"%{search_query}%"])
        SQL += " ORDER BY p.post_id DESC"
        
        with conn.cursor() as cursor:
            cursor.execute(SQL, params)
            posts = cursor.fetchall()
        
        for post in posts:
            if post.get('created_at'): post['created_at'] = post['created_at'].strftime('%Y-%m-%dT%H:%M:%S.000Z')
            
        return jsonify(posts), 200
    except Exception as e:
        print(f"게시글 목록 조회 중 서버 오류 발생: {e}")
        return jsonify({"error": "게시글 목록을 불러오는 데 실패했습니다."}), 500
    finally:
        if conn: conn.close()

# 게시글 작성 (POST /posts) - JWT 인증
@app.route('/posts', methods=['POST'])
@token_required 
def create_post():
    data = request.get_json()
    title = data.get('title')
    content = data.get('content')
    user_id = request.user_id # 토큰에서 추출한 user_id
    
    if not all([title, content]):
        return jsonify({"error": "제목과 내용이 필요합니다."}), 400
    conn = get_db_connection()
    if conn is None: return jsonify({"error": "DB 연결 실패"}), 500
    try:
        with conn.cursor() as cursor:
            SQL = "INSERT INTO posts (user_id, title, content, views, created_at) VALUES (%s, %s, %s, 0, NOW())"
            cursor.execute(SQL, (user_id, title, content))
        conn.commit()
        return jsonify({"message": "게시글이 성공적으로 작성되었습니다.", "postId": cursor.lastrowid}), 201
    except Exception as e:
        print(f"게시글 작성 중 서버 오류 발생: {e}")
        return jsonify({"error": "게시글 작성 중 서버 오류가 발생했습니다."}), 500
    finally:
        if conn: conn.close()

# ⬇️ [신규 추가] 게시글 상세 조회 (GET /posts/<id>)
@app.route('/posts/<int:post_id>', methods=['GET'])
def get_post_detail(post_id):
    conn = get_db_connection()
    if conn is None: return jsonify({"error": "DB 연결 실패"}), 500
    try:
        with conn.cursor() as cursor:
            # 1. 조회수 증가 (Node.js 로직과 동일)
            cursor.execute("UPDATE posts SET views = views + 1 WHERE post_id = %s", (post_id,))
            
            # 2. 게시글 상세 정보 조회
            SQL = """
                SELECT p.*, u.nickname AS authorName
                FROM posts p
                LEFT JOIN users u ON p.user_id = u.user_id
                WHERE p.post_id = %s
            """
            cursor.execute(SQL, (post_id,))
            post = cursor.fetchone()
        
        conn.commit() # 조회수 증가 반영
        
        if not post:
            return jsonify({"error": "게시글을 찾을 수 없습니다."}), 404
        
        # 날짜 포맷팅
        if post.get('created_at'): post['created_at'] = post['created_at'].strftime('%Y-%m-%dT%H:%M:%S.000Z')
        if post.get('updated_at'): post['updated_at'] = post['updated_at'].strftime('%Y-%m-%dT%H:%M:%S.000Z')

        return jsonify(post), 200
    except Exception as e:
        conn.rollback() # 오류 발생 시 조회수 증가 롤백
        print(f"게시글 상세 조회 오류: {e}")
        return jsonify({"error": "게시글을 불러오는 데 실패했습니다."}), 500
    finally:
        if conn: conn.close()

# ⬇️ [신규 추가] 게시글 수정 (PUT /posts/<id>) - JWT 인증
@app.route('/posts/<int:post_id>', methods=['PUT'])
@token_required
def update_post(post_id):
    data = request.get_json()
    title = data.get('title')
    content = data.get('content')
    user_id_from_token = request.user_id # 토큰에서 추출한 user_id
    
    if not all([title, content]):
        return jsonify({"error": "제목과 내용이 필요합니다."}), 400
    
    conn = get_db_connection()
    if conn is None: return jsonify({"error": "DB 연결 실패"}), 500
    try:
        with conn.cursor() as cursor:
            # 1. 게시글 작성자 확인
            cursor.execute("SELECT user_id FROM posts WHERE post_id = %s", (post_id,))
            post = cursor.fetchone()
            if not post:
                return jsonify({"error": "게시글을 찾을 수 없습니다."}), 404
            
            # 2. 소유권 확인 (토큰의 user_id와 게시글의 user_id 비교)
            if post['user_id'] != user_id_from_token:
                return jsonify({"error": "게시글 수정 권한이 없습니다."}), 403
            
            # 3. 게시글 업데이트
            SQL = "UPDATE posts SET title = %s, content = %s, updated_at = NOW() WHERE post_id = %s"
            cursor.execute(SQL, (title, content, post_id))
        
        conn.commit()
        return jsonify({"message": "게시글이 성공적으로 수정되었습니다."}), 200
    except Exception as e:
        conn.rollback()
        print(f"게시글 수정 오류: {e}")
        return jsonify({"error": "게시글 수정 중 서버 오류가 발생했습니다."}), 500
    finally:
        if conn: conn.close()

# ⬇️ [신규 추가] 게시글 삭제 (DELETE /posts/<id>) - JWT 인증
@app.route('/posts/<int:post_id>', methods=['DELETE'])
@token_required
def delete_post(post_id):
    user_id_from_token = request.user_id # 토큰에서 추출한 user_id
    
    conn = get_db_connection()
    if conn is None: return jsonify({"error": "DB 연결 실패"}), 500
    try:
        with conn.cursor() as cursor:
            # 1. 게시글 작성자 확인
            cursor.execute("SELECT user_id FROM posts WHERE post_id = %s", (post_id,))
            post = cursor.fetchone()
            if not post:
                return jsonify({"error": "게시글을 찾을 수 없습니다."}), 404
            
            # 2. 소유권 확인
            if post['user_id'] != user_id_from_token:
                return jsonify({"error": "게시글 삭제 권한이 없습니다."}), 403
            
            # 3. 댓글 먼저 삭제 (외래키 제약조건)
            cursor.execute("DELETE FROM comments WHERE post_id = %s", (post_id,))
            
            # 4. 게시글 삭제
            cursor.execute("DELETE FROM posts WHERE post_id = %s", (post_id,))
            
        conn.commit()
        return jsonify({"message": "게시글이 성공적으로 삭제되었습니다."}), 200
    except Exception as e:
        conn.rollback()
        print(f"게시글 삭제 오류: {e}")
        return jsonify({"error": "게시글 삭제 중 서버 오류가 발생했습니다."}), 500
    finally:
        if conn: conn.close()


# =======================================================
# 9. 댓글 API (Node.js 로직 이식 완료)
# =======================================================

# 댓글 목록 조회 (GET /posts/<id>/comments)
@app.route('/posts/<int:post_id>/comments', methods=['GET'])
def get_comments(post_id):
    conn = get_db_connection()
    if conn is None: return jsonify({"error": "DB 연결 실패"}), 500
    try:
        with conn.cursor() as cursor:
            # 닉네임을 가져오기 위해 users 테이블과 JOIN
            SQL = """
                SELECT c.*, u.nickname AS authorName
                FROM comments c
                LEFT JOIN users u ON c.user_id = u.user_id
                WHERE c.post_id = %s
                ORDER BY c.created_at ASC
            """
            cursor.execute(SQL, (post_id,))
            comments = cursor.fetchall()
            
        for comment in comments:
            if comment.get('created_at'): comment['created_at'] = comment['created_at'].strftime('%Y-%m-%dT%H:%M:%S.000Z')

        return jsonify(comments), 200
    except Exception as e:
        print(f"댓글 목록 로드 오류: {e}")
        return jsonify({"error": "댓글 목록을 불러오는 데 실패했습니다."}), 500
    finally:
        if conn: conn.close()

# 댓글 작성 (POST /posts/<id>/comments) - JWT 인증
@app.route('/posts/<int:post_id>/comments', methods=['POST'])
@token_required
def create_comment(post_id):
    data = request.get_json()
    content = data.get('content')
    user_id = request.user_id # 토큰에서 추출
    
    if not content:
        return jsonify({"error": "댓글 내용을 입력해야 합니다."}), 400

    conn = get_db_connection()
    if conn is None: return jsonify({"error": "DB 연결 실패"}), 500
    try:
        with conn.cursor() as cursor:
            SQL = "INSERT INTO comments (post_id, user_id, content, created_at) VALUES (%s, %s, %s, NOW())"
            cursor.execute(SQL, (post_id, user_id, content))
        
        conn.commit()
        return jsonify({"message": "댓글 작성 성공", "commentId": cursor.lastrowid}), 201
    except Exception as e:
        print(f"댓글 작성 오류: {e}")
        return jsonify({"error": "댓글 작성 중 서버 오류가 발생했습니다."}), 500
    finally:
        if conn: conn.close()

# =======================================================
# 10. Gunicorn 또는 로컬 테스트용 실행
# =======================================================
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=80, debug=True)