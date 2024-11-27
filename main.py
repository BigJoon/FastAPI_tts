from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.websockets import WebSocket
import httpx
import json
import os
from typing import Dict
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()
active_connections: Dict[str, WebSocket] = {}

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# GPU 서버 URL 환경변수에서 가져오기
GPU_SERVER_URL = os.getenv('GPU_SERVER_URL')

@app.websocket("/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: str):
    await websocket.accept()
    active_connections[client_id] = websocket
    try:
        # GPU 서버의 웹소켓에 연결
        async with httpx.AsyncClient() as client:
            gpu_ws_url = GPU_SERVER_URL.replace('https://', 'wss://')
            async with client.websocket(f"{gpu_ws_url}/ws/{client_id}") as gpu_ws:
                while True:
                    data = await gpu_ws.receive_text()
                    await websocket.send_text(data)
    except Exception as e:
        print(f"WebSocket 에러: {str(e)}")
    finally:
        if client_id in active_connections:
            del active_connections[client_id]

@app.post("/generate-tts")
async def generate_tts(
    text_data: str = Form(...),
    speaker_file: UploadFile = File(...),
    client_id: str = Form(...)
):
    try:
        # GPU 서버로 요청 전달
        async with httpx.AsyncClient() as client:
            form_data = {
                'text_data': text_data,
                'client_id': client_id
            }
            files = {
                'speaker_file': (speaker_file.filename, await speaker_file.read())
            }
            
            print(f"Forwarding request to GPU server: {GPU_SERVER_URL}")  # URL 로깅
            
            response = await client.post(
                f"{GPU_SERVER_URL}/generate-tts",
                data=form_data,
                files=files
            )
            
            if response.status_code != 200:
                error_content = await response.text()  # 에러 응답 내용 확인
                print(f"GPU server error: {error_content}")  # 에러 내용 로깅
                raise HTTPException(status_code=response.status_code, detail=f"GPU 서버 처리 실패: {error_content}")
            
            return StreamingResponse(
                response.iter_bytes(),
                media_type="audio/wav"
            )

    except Exception as e:
        print(f"상세 에러 발생: {str(e)}")  # 상세 에러 로깅
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/test")
async def test_endpoint():
    return {"status": "ok", "message": "Cloud server is running!"}

@app.get("/test-gpu-connection")
async def test_gpu_connection():
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{GPU_SERVER_URL}/test")
            return {
                "status": "ok",
                "gpu_server": GPU_SERVER_URL,
                "gpu_response": response.json()
            }
    except Exception as e:
        return {
            "status": "error",
            "message": str(e),
            "gpu_server": GPU_SERVER_URL
        }

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv('PORT', 8080))  # Azure는 기본적으로 8080 포트를 사용
    uvicorn.run(app, host="0.0.0.0", port=port) 
