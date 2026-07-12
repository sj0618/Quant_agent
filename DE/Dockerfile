FROM apache/airflow:2.9.1

# 1. TA-Lib C 라이브러리 및 파이썬 컴파일용 필수 도구 설치 (root 권한)
USER root
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    wget \
    && wget -O ta-lib-0.4.0-src.tar.gz https://sourceforge.net/projects/ta-lib/files/ta-lib/0.4.0/ta-lib-0.4.0-src.tar.gz/download \
    && tar -xzf ta-lib-0.4.0-src.tar.gz \
    && cd ta-lib/ \
    && ./configure --prefix=/usr \
    && make \
    && make install \
    && cd .. && rm -rf ta-lib* \
    && rm -rf /var/lib/apt/lists/*

# C 라이브러리 경로 이정표 설치
ENV TA_INCLUDE_PATH=/usr/include
ENV TA_LIBRARY_PATH=/usr/lib

# 2. 에어플로우 안전 계정으로 복귀
USER airflow

# 3.TA-Lib 컴파일 지뢰 제거 핵심 패치
ARG PIP_CONSTRAINT=""
# 에어플로우 2.9와 호환되는 안전한 넘파이 1.x 버전을 먼저 설치합니다.
RUN pip install --no-cache-dir numpy==1.26.4
# 빌드 격리를 해제(--no-build-isolation)하여 위에서 깐 넘파이를 참조해 TA-Lib을 성공적으로 구워냅니다.
RUN pip install --no-cache-dir --no-build-isolation TA-Lib==0.6.8

# 4. 나머지 패키지 목록 복사 및 설치 (이미 깔린 numpy와 TA-Lib은 알아서 스킵됩니다)
COPY requirements.txt /requirements.txt
RUN pip install --no-cache-dir -r /requirements.txt