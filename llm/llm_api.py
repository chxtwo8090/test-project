from fastapi import FastAPI
from pydantic import BaseModel
from llama_cpp import Llama
from starlette.responses import JSONResponse
import os
import time
import boto3
from botocore.exceptions import ClientError

# --- 환경 설정 (업데이트됨) ---
MODEL_FILE_NAME = "gemma-3n-E4B-it-Q4_K_M.gguf" # 🔑 수정된 모델 파일 이름
S3_BUCKET_NAME = os.environ.get("S3_BUCKET_NAME")
S3_MODEL_KEY = os.environ.get("S3_MODEL_KEY", MODEL_FILE_NAME) 
MODEL_LOCAL_PATH = f"/tmp/{MODEL_FILE_NAME}" 

# --- 모델 다운로드 함수 (이전과 동일) ---
def download_model_from_s3(bucket_name, key, local_path):
    """S3에서 GGUF 모델 파일을 다운로드합니다."""
    if not bucket_name or not key:
        print("ERROR: S3 환경 변수가 설정되지 않았습니다.")
        return False
        
    print(f"S3에서 모델 다운로드 시작: s3://{bucket_name}/{key}")
    try:
        s3 = boto3.client('s3')
        os.makedirs(os.path.dirname(local_path) or '.', exist_ok=True)
        s3.download_file(bucket_name, key, local_path)
        print("모델 다운로드 완료.")
        return True
    except ClientError as e:
        if e.response['Error']['Code'] == "404":
            print(f"ERROR: S3 객체 {key}를 버킷 {bucket_name}에서 찾을 수 없습니다.")
        else:
            print(f"ERROR: S3 다운로드 중 예상치 못한 오류 발생: {e}")
        return False
    except Exception as e:
        print(f"모델 다운로드 실패! 오류: {e}")
        return False

# --- 모델 초기화 및 FastAPI 엔드포인트 로직은 이전과 동일하게 유지 ---
llm = None
if download_model_from_s3(S3_BUCKET_NAME, S3_MODEL_KEY, MODEL_LOCAL_PATH):
    try:
        llm = Llama(
            model_path=MODEL_LOCAL_PATH,
            n_gpu_layers=0,  
            n_ctx=4096,      
            verbose=False    
        )
        print("LLM Model Loaded Successfully!")
    except Exception as e:
        print(f"ERROR: Failed to load LLM model from {MODEL_LOCAL_PATH}. Error: {e}")
        llm = None

app = FastAPI(
    title="Gemma 3N Financial Chat API",
    description="AWS Fargate에서 S3 모델을 사용하는 LLM 추론 API입니다.",
)

class ChatRequest(BaseModel):
    prompt: str

class ChatResponse(BaseModel):
    response: str
    time_ms: int

@app.get("/health")
def health_check():
    if llm is None:
        return JSONResponse(status_code=503, content={"status": "DOWN", "message": "LLM not loaded or failed to download"})
    return {"status": "UP", "model_path": MODEL_LOCAL_PATH}

@app.post("/llm/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    if llm is None:
        return JSONResponse(status_code=503, content={"error": "LLM 서버 준비 안 됨"},)

    start_time = time.time()
    
    prompt_template = f"""
    당신은 gemma-3n-E4B-it 기반의 전문 금융 분석가 챗봇입니다.
    사용자 질문에 대해 간결하고 정확하게 답변하며, 현재 금융 시장 및 데이터와 관련하여 전문적인 인사이트를 제공합니다.

    User: {request.prompt}
    Assistant:
    """

    try:
        output = llm(
            prompt_template, 
            max_tokens=1024, 
            stop=["\nUser:", "User:"], 
            echo=False,
            temperature=0.7 
        )
        
        response_text = output['choices'][0]['text'].strip()
        end_time = time.time()
        
        return ChatResponse(
            response=response_text,
            time_ms=int((end_time - start_time) * 1000)
        )
    
    except Exception as e:
        print(f"LLM 추론 오류: {e}")
        return JSONResponse(
            status_code=500, 
            content={"error": f"LLM 추론 중 오류 발생: {e}"}
        )