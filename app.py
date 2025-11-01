from flask import Flask

# Flask 앱 객체를 'app'이라는 이름으로 생성합니다.
# (Dockerfile의 'app:app'과 일치)
app = Flask(__name__)

@app.route('/')
def hello():
    # 이 메시지가 보이면 EKS 배포에 최종 성공한 것입니다.
    return "Hello, EKS! It is finally working!"

if __name__ == '__main__':
    # (이 부분은 Gunicorn이 실행할 때는 사용되지 않습니다)
    app.run(host='0.0.0.0', port=8000)