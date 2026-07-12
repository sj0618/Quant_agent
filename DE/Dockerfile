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

ENV PIP_CONSTRAINT=""

# 1. 고정할 핵심 뼈대 선설치
RUN pip install --no-cache-dir numpy==1.26.4
RUN pip install --no-cache-dir --no-build-isolation TA-Lib==0.6.8

# 2. 깨끗해진 requirements.txt 패키지들 정상 설치
COPY requirements.txt /requirements.txt
RUN pip install --no-cache-dir -r /requirements.txt

# 3. [대망의 필살기] 의존성 족보 싸움을 무시하고 pandas-ta 강제 주입
# PyPI에서 최신 버전을 다운로드하되, 넘파이 버전 체크를 건너뛰고 1.26.4 위에 안전하게 안착시킵니다.
RUN pip install --no-cache-dir --no-deps pandas-ta