# syntax=docker/dockerfile:1

FROM ubuntu:24.04 AS build

WORKDIR /CORE

# Install core build dependencies (merged into one step for speed)
RUN apt-get update && \
    DEBIAN_FRONTEND=noninteractive TZ=Etc/UTC apt-get install -y \
    tzdata \
    software-properties-common \
    ninja-build \
    python3 python3-pip python3-venv \
    wget \
    git \
    cmake \
    build-essential \         
    pkg-config \              
    libssl-dev \              
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Install Clang 19
RUN wget https://apt.llvm.org/llvm.sh && chmod +x llvm.sh && ./llvm.sh 19

RUN mkdir /clang && \
    ln -s /usr/bin/clang-19  /clang/clang && \
    ln -s /usr/bin/clang++-19 /clang/clang++

ENV PATH="/clang:$PATH"

# Python environment
RUN python3 -m venv py
ENV PATH="/CORE/py/bin:$PATH"

RUN pip install --no-cache-dir conan
RUN conan profile detect
RUN conan remote add artifactory https://conan.buzeta.net/artifactory/api/conan/conan-local

COPY . .
RUN chmod +x /CORE/scripts/*.sh

ENV TRACY_NO_INVARIANT_CHECK=1

RUN scripts/build.sh -b Release

RUN cp -r python_streamer/coinbase/* /CORE/build/Release


FROM ubuntu:24.04 AS final

WORKDIR /CORE

RUN apt-get update && \
    apt-get install -y python3 python3-pip python3.12-venv && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

RUN python3 -m venv py
ENV PATH="/CORE/py/bin:$PATH"

COPY --from=build /CORE/requirements.txt /CORE/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY --from=build /CORE/build/Release /CORE/build/Release

CMD ["/bin/bash"]
