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

ARG PIP_CONSTRAINT=""

# 1. 빌드에 필요한 핵심 도구(setuptools, wheel, Cython 3이상)와 NumPy 버전을 먼저 고정 설치
RUN pip install --no-cache-dir "setuptools>=67.0.0" wheel "Cython>=3.0.0" numpy==1.26.4 meson-python

# 2. 이미 설치된 안전한 환경을 참조하여 TA-Lib을 컴파일
RUN pip install --no-cache-dir --no-build-isolation TA-Lib==0.6.8

# 3. [핵심] requirements.txt를 설치할 때도 --no-build-isolation 플래그를 추가
# 위에서 깔아놓은 안전한 Cython과 NumPy를 사용하여 pandas를 빌드
COPY requirements.txt /requirements.txt
RUN pip install --no-cache-dir --no-build-isolation -r /requirements.txt