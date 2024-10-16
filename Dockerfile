# Python slim 이미지로 시작
FROM python:3.9-slim

# Package Install
RUN apt-get update && apt-get -y upgrade && apt-get -y install git net-tools vim

# 작업 디렉토리 설정
WORKDIR /root/TripPassFastAPI

# 애플리케이션 코드 복사
COPY . .

# 가상 환경 생성 및 패키지 설치
RUN python3.9 -m venv .venv
RUN ./.venv/bin/pip install --upgrade pip
RUN ./.venv/bin/pip install -r requirements.txt

# 애플리케이션이 실행될 포트 설정
EXPOSE 3000

# 애플리케이션 시작 명령어
CMD [".venv/bin/uvicorn", "app:app", "--host", "0.0.0.0", "--port", "3000", "--reload"]