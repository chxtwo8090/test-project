import os
import pymysql
import bcrypt
import jwt
import requests  # ⬅️ [추가] 웹 요청 라이브러리
from bs4 import BeautifulSoup  # ⬅️ [추가] HTML 파싱 라이브러리
from datetime import datetime, timedelta
from functools import wraps
from flask import Flask, request, jsonify
from flask_cors import CORS

# =======================================================
# 1. Flask 애플리케이션 초기 설정
# =======================================================
app = Flask(__name__)
# S3 웹사이트 주소만 허용 (사용자님의 S3 주소에 맞춰 수정되었습니다.)
CORS(app, resources={r"/*": {"origins": "http://chxtwo-git.s3-website.ap-northeast-2.amazonaws.com"}})
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
# =======================================================
def token_required(f):
    """JWT 토큰 유효성을 검증하는 데코레이터"""
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        # Authorization 헤더에서 토큰 추출 (Bearer <token>)
        if 'Authorization' in request.headers:
            auth_header = request.headers['Authorization']
            try:
                # 'Bearer '를 제외한 순수 토큰만 추출
                token = auth_header.split(" ")[1]
            except IndexError:
                return jsonify({'message': 'Authorization 헤더 형식이 잘못되었습니다.'}), 401

        if not token:
            return jsonify({'message': '토큰이 누락되었습니다. 로그인이 필요합니다.'}), 401

        try:
            # 토큰 디코딩 및 검증
            data = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
            # 요청 객체에 사용자 ID와 닉네임 저장
            request.user_id = data['user_id']
            request.nickname = data['nickname']
        except jwt.ExpiredSignatureError:
            return jsonify({'message': '토큰이 만료되었습니다. 다시 로그인해주세요.'}), 401
        except jwt.InvalidTokenError:
            return jsonify({'message': '유효하지 않은 토큰입니다.'}), 401
        except Exception as e:
            print(f"토큰 검증 중 알 수 없는 오류: {e}")
            return jsonify({'message': '서버 오류로 인해 인증에 실패했습니다.'}), 500

        return f(*args, **kwargs)
    return decorated

# =======================================================
# 5. 회원가입 API
# =======================================================
@app.route('/register', methods=['POST'])
def register_user():
    data = request.get_json()
    username = data.get('username')
    nickname = data.get('nickname')
    password = data.get('password')

    if not all([username, nickname, password]):
        return jsonify({"message": "필수 정보가 누락되었습니다."}), 400

    conn = get_db_connection()
    if conn is None:
        return jsonify({"message": "데이터베이스 연결에 실패했습니다."}), 500
    
    # 비밀번호 해싱
    hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())

    try:
        with conn.cursor() as cursor:
            # 1. 아이디 중복 확인
            cursor.execute("SELECT user_id FROM users WHERE username = %s", (username,))
            if cursor.fetchone():
                return jsonify({"message": "이미 사용 중인 아이디입니다."}), 409 # Conflict

            # 2. 사용자 정보 삽입
            SQL = "INSERT INTO users (username, nickname, password_hash) VALUES (%s, %s, %s)"
            # 해시된 비밀번호는 문자열로 저장
            cursor.execute(SQL, (username, nickname, hashed_password.decode('utf-8')))
        
        conn.commit()
        return jsonify({"message": "회원가입에 성공했습니다."}), 201

    except pymysql.err.IntegrityError as e:
        print(f"회원가입 중 데이터 무결성 오류: {e}")
        return jsonify({"message": "데이터 처리 중 오류가 발생했습니다. (중복된 닉네임 등)"}), 409
    except Exception as e:
        print(f"회원가입 중 서버 오류 발생: {e}")
        return jsonify({"message": "회원가입 중 서버 오류가 발생했습니다."}), 500
    finally:
        if conn: conn.close()

# =======================================================
# 6. 로그인 API
# =======================================================
@app.route('/login', methods=['POST'])
def login_user():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')

    if not all([username, password]):
        return jsonify({"message": "아이디와 비밀번호를 모두 입력해주세요."}), 400

    conn = get_db_connection()
    if conn is None:
        return jsonify({"message": "데이터베이스 연결에 실패했습니다."}), 500

    try:
        with conn.cursor() as cursor:
            # 1. 사용자 조회 (ID, 해시된 비밀번호, 닉네임)
            SQL = "SELECT user_id, nickname, password_hash FROM users WHERE username = %s"
            cursor.execute(SQL, (username,))
            user = cursor.fetchone()

            if not user:
                return jsonify({"message": "아이디 또는 비밀번호를 잘못 입력했습니다."}), 401
            
            # DB에서 가져온 해시 값과 입력된 비밀번호를 비교
            stored_hash = user['password_hash'].encode('utf-8')
            input_password_bytes = password.encode('utf-8')
            
            if not bcrypt.checkpw(input_password_bytes, stored_hash):
                return jsonify({"message": "아이디 또는 비밀번호를 잘못 입력했습니다."}), 401

            # 3. 인증 성공: JWT 토큰 생성
            payload = {
                'user_id': user['user_id'],
                'nickname': user['nickname'],
                'exp': datetime.utcnow() + timedelta(hours=24)
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
        if conn: conn.close()


# =======================================================
# 7. 게시글 목록 조회 API (GET /posts)
# =======================================================
@app.route('/posts', methods=['GET'])
def list_posts():
    conn = get_db_connection()
    if conn is None: return jsonify({"message": "DB 연결 실패"}), 500

    try:
        with conn.cursor() as cursor:
            # JOIN을 통해 게시글 정보와 작성자 닉네임을 함께 가져옵니다.
            SQL = """
            SELECT 
                p.post_id, p.title, p.content, 
                p.created_at, p.updated_at,
                u.nickname AS author_nickname,
                (SELECT COUNT(*) FROM comments c WHERE c.post_id = p.post_id) AS comment_count
            FROM posts p
            JOIN users u ON p.user_id = u.user_id
            ORDER BY p.post_id DESC
            """
            cursor.execute(SQL)
            posts = cursor.fetchall()
            
            # Datetime 객체를 JSON 직렬화가 가능한 문자열로 변환
            for post in posts:
                post['created_at'] = post['created_at'].strftime('%Y-%m-%d %H:%M')
                # updated_at은 Null일 수 있으므로 안전하게 처리
                if post['updated_at']:
                    post['updated_at'] = post['updated_at'].strftime('%Y-%m-%d %H:%M')
                else:
                    post['updated_at'] = None

        return jsonify(posts), 200

    except Exception as e:
        print(f"게시글 목록 조회 중 서버 오류 발생: {e}")
        return jsonify({"message": "게시글 목록 조회 중 서버 오류가 발생했습니다."}), 500
    finally:
        if conn: conn.close()


# =======================================================
# 8. 게시글 작성 API (POST /posts)
# =======================================================
@app.route('/posts', methods=['POST'])
@token_required 
def create_post():
    data = request.get_json()
    title = data.get('title')
    content = data.get('content')
    
    user_id = request.user_id 
    
    if not all([title, content]):
        return jsonify({"message": "제목과 내용을 모두 입력해주세요."}), 400

    conn = get_db_connection()
    if conn is None: return jsonify({"message": "DB 연결 실패"}), 500

    try:
        with conn.cursor() as cursor:
            SQL = "INSERT INTO posts (user_id, title, content) VALUES (%s, %s, %s)"
            cursor.execute(SQL, (user_id, title, content))

        conn.commit()
        return jsonify({"message": "게시글 작성 성공", "post_id": cursor.lastrowid}), 201

    except Exception as e:
        print(f"게시글 작성 중 서버 오류 발생: {e}")
        return jsonify({"message": "게시글 작성 중 서버 오류가 발생했습니다."}), 500
    finally:
        if conn: conn.close()


# =======================================================
# 9. 댓글 관련 API (댓글 조회, 작성)
# =======================================================

@app.route('/posts/<int:post_id>/comments', methods=['GET'])
def list_comments(post_id):
    conn = get_db_connection()
    if conn is None: return jsonify({"message": "DB 연결 실패"}), 500

    try:
        with conn.cursor() as cursor:
            # 댓글 내용과 작성자 닉네임을 조회
            SQL = """
            SELECT 
                c.comment_id, c.content, c.created_at,
                u.nickname AS author_nickname 
            FROM comments c
            JOIN users u ON c.user_id = u.user_id
            WHERE c.post_id = %s
            ORDER BY c.created_at ASC
            """
            cursor.execute(SQL, (post_id,))
            comments = cursor.fetchall()

            for comment in comments:
                comment['created_at'] = comment['created_at'].strftime('%Y-%m-%d %H:%M')

        return jsonify(comments), 200
        
    except Exception as e:
        print(f"댓글 목록 조회 중 서버 오류 발생: {e}")
        return jsonify({"message": "댓글 목록 조회 중 서버 오류가 발생했습니다."}), 500
    finally:
        if conn: conn.close()


@app.route('/posts/<int:post_id>/comments', methods=['POST'])
@token_required
def create_comment(post_id):
    data = request.get_json()
    content = data.get('content')
    
    user_id = request.user_id
    
    if not content:
        return jsonify({"message": "댓글 내용을 입력해주세요."}), 400

    conn = get_db_connection()
    if conn is None: return jsonify({"message": "DB 연결 실패"}), 500

    try:
        with conn.cursor() as cursor:
            SQL = "INSERT INTO comments (post_id, user_id, content) VALUES (%s, %s, %s)"
            cursor.execute(SQL, (post_id, user_id, content))
        
        conn.commit()
        return jsonify({"message": "댓글 작성 성공", "comment_id": cursor.lastrowid}), 201

    except Exception as e:
        print(f"댓글 작성 중 서버 오류 발생: {e}")
        return jsonify({"message": "댓글 작성 중 서버 오류가 발생했습니다."}), 500
    finally:
        if conn: conn.close()


# =======================================================
# 10. [신규] 금융 정보 API (크롤링)
# =======================================================
@app.route('/api/finance/summary', methods=['GET'])
def get_finance_summary():
    """네이버 증시에서 KOSPI, KOSDAQ 지수를 크롤링합니다."""
    
    url = "https://finance.naver.com/"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }

    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status() # 200 OK가 아니면 에러 발생

        soup = BeautifulSoup(response.text, 'html.parser')

        # 🚨 [수정] CSS 선택자를 찾지 못할 경우 'N/A'로 안전하게 처리하여 AttributeError 방지
        # kospi
        kospi_element = soup.select_one('#KOSPI_now')
        kospi_val = kospi_element.text if kospi_element else 'N/A'
        kospi_change_element = soup.select_one('#KOSPI_change')
        kospi_change = kospi_change_element.text.strip() if kospi_change_element else 'N/A'
        
        # kosdaq
        kosdaq_element = soup.select_one('#KOSDAQ_now')
        kosdaq_val = kosdaq_element.text if kosdaq_element else 'N/A'
        kosdaq_change_element = soup.select_one('#KOSDAQ_change')
        kosdaq_change = kosdaq_change_element.text.strip() if kosdaq_change_element else 'N/A'

        # 찾은 데이터를 JSON으로 반환
        return jsonify({
            "kospi": {
                "value": kospi_val,
                "change": kospi_change
            },
            "kosdaq": {
                "value": kosdaq_val,
                "change": kosdaq_change
            }
        }), 200

    except Exception as e:
        # 💡 [수정] 에러 상세 내용(str(e))을 응답에 포함시켜 브라우저로 반환
        error_detail = str(e)
        print(f"금융 정보 크롤링 오류: {error_detail}")
        
        # 400 Bad Request와 에러 상세 정보를 반환하여 디버깅 용이하게 함
        return jsonify({
            "error": "금융 정보를 가져오는 데 실패했습니다.", 
            "detail": error_detail
        }), 400

# =======================================================
# 11. Gunicorn 또는 로컬 테스트용 실행
# =======================================================
if __name__ == '__main__':
    # 로컬 테스트 시 디버그 모드 사용
    app.run(host='0.0.0.0', port=80, debug=True)