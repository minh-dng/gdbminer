# syntax=docker/dockerfile:1.7
# This Dockerfile builds an image to run benchmark experiments in
# Copyright (c) 2023 Robert Bosch GmbH
# SPDX-License-Identifier: AGPL-3.0

FROM ubuntu:18.04
# Mimid's requirements are available for ubuntu 18, only

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

COPY --from=ghcr.io/astral-sh/uv:0.11.1 /uv /uvx /usr/local/bin/

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt/lists,sharing=locked \
    rm -f /etc/apt/apt.conf.d/docker-clean \
    && echo 'Binary::apt::APT::Keep-Downloaded-Packages "true";' > /etc/apt/apt.conf.d/keep-cache \
    && apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install --no-install-recommends -y \
    build-essential openjdk-11-jdk-headless graphviz graphviz-dev software-properties-common   git  \
    ninja-build subversion pkg-config  llvm-4.0 llvm-4.0-dev zlib1g-dev nano \
    libclang-8-dev clang-format-8 clang-8 clang-4.0 jq \
    autoconf dh-autoreconf automake libtool libjson-c-dev \
    wget ca-certificates checkinstall  liblzma-dev \
    libreadline-gplv2-dev libncursesw5-dev libssl-dev \
    libsqlite3-dev tk-dev libgdbm-dev libc6-dev libbz2-dev libffi-dev \
    python3-pip python3-venv python3-distutils python3-dev python-dev autotools-dev libicu-dev libboost-all-dev \
    python3-software-properties python3-apt texinfo libc6-dbg libcairo2-dev

RUN ln -s /usr/bin/clang-8 /usr/bin/clang
ENV UV_PROJECT_ENVIRONMENT=/opt/gdbminer-venv \
    UV_PYTHON=3.9.17 \
    UV_CACHE_DIR=/root/.cache/uv \
    UV_LINK_MODE=copy \
    PATH="/opt/gdbminer-venv/bin:$PATH"
RUN     mkdir -p /GDBMiner /tmp/build
COPY    pyproject.toml uv.lock README.md LICENSE setup.py setup.cfg /GDBMiner/
RUN --mount=type=cache,target=/root/.cache/uv \
        uv sync --project /GDBMiner --frozen --no-dev --no-install-project

WORKDIR /tmp/build

RUN wget -O gdb-9.2.tar.gz https://ftp.gnu.org/gnu/gdb/gdb-9.2.tar.gz && \
    tar -xf gdb-9.2.tar.gz && cd gdb-9.2 && mkdir build && cd build && \
    ../configure && make -j"$(nproc)" && make install && \
    rm -rf /tmp/build/*
    

RUN wget -O valgrind-3.21.0.tar.bz2 https://sourceware.org/pub/valgrind/valgrind-3.21.0.tar.bz2 && \
    tar -xf valgrind-3.21.0.tar.bz2 && cd valgrind-3.21.0 && \
    ./configure && make -j"$(nproc)" && make install && \
    rm -rf /tmp/build/*

ARG JSON_C_COMMIT=ee9f67c81a3c2a44557f0cc16dc136c140293252
RUN mkdir json-c && \
    wget -O json-c.tar.gz "https://github.com/json-c/json-c/archive/${JSON_C_COMMIT}.tar.gz" && \
    tar -xf json-c.tar.gz --strip-components=1 -C json-c && \
    cd json-c && \
    sh autogen.sh && ./configure && make -j"$(nproc)" && make install && \
    rm -rf /tmp/build/*
    
ARG TARGETARCH
RUN case "${TARGETARCH:-$(dpkg --print-architecture)}" in \
        amd64) CMAKE_ARCH=x86_64 ;; \
        arm64) CMAKE_ARCH=aarch64 ;; \
        *) echo "Unsupported architecture: ${TARGETARCH:-$(dpkg --print-architecture)}" && exit 1 ;; \
    esac && \
    wget "https://github.com/Kitware/CMake/releases/download/v3.29.0-rc2/cmake-3.29.0-rc2-linux-${CMAKE_ARCH}.sh" -O /tmp/cmake.sh && \
    chmod a+x /tmp/cmake.sh && \
    bash /tmp/cmake.sh --skip-license --prefix=/usr/local --exclude-subdir && \
    rm /tmp/cmake.sh

# Compile static libxml
RUN wget -O libxml2-2.12.4.tar.xz https://download.gnome.org/sources/libxml2/2.12/libxml2-2.12.4.tar.xz && \
    tar -xf libxml2-2.12.4.tar.xz && cd libxml2-2.12.4 && mkdir build && cd build && \
    cmake -D LIBXML2_WITH_ZLIB=OFF -D LIBXML2_WITH_LZMA=OFF  -DLIBXML2_WITH_ICONV=OFF -DLIBXML2_WITH_THREADS=OFF -DBUILD_SHARED_LIBS=OFF -DCMAKE_BUILD_TYPE=Debug -DCMAKE_C_FLAGS="-O0" ..  && \
    make -j"$(nproc)" && make install && ldconfig && \
    rm -rf /tmp/build/*
    
RUN (wget -O boost_1_80_0.tar.gz https://archives.boost.io/release/1.80.0/source/boost_1_80_0.tar.gz || \
    wget -O boost_1_80_0.tar.gz https://sourceforge.net/projects/boost/files/boost/1.80.0/boost_1_80_0.tar.gz/download) && \
    tar -xf boost_1_80_0.tar.gz && cd boost_1_80_0 && ./bootstrap.sh --prefix=/usr/local --with-toolset=gcc && \
    ./b2 toolset=gcc && ./b2 install && \
    rm -rf /tmp/build/*

    
RUN git clone --depth 1 --single-branch https://github.com/vrthra/mimid.git /mimid


RUN cd /mimid && tar -xf taints.tar.gz && cd taints && \
    meson build/debug --prefix="$(pwd)/install" && \
    ninja -C build/debug install

RUN sed -i 's+pfuzzer=../../taints+pfuzzer=../taints+g' /mimid/Cmimid/Makefile


RUN git clone --branch master --single-branch --depth 1 https://github.com/neil-kulkarni/arvada.git /arvada

RUN git clone --branch master --single-branch --depth 1 https://github.com/rifatarefin/treevada /treevada


WORKDIR /

COPY    src /GDBMiner/src
COPY    example_programs /example_programs

# Compile svgpp
#RUN cd example_programs/svgcpp/svgpp/src/demo/render/ && mkdir build && cd build && \
#    cmake -DCMAKE_BUILD_TYPE=Debug -DCMAKE_CXX_FLAGS="-O0 -DDEBUG" .. &&  make

 
    
COPY    fetch_example_programs.sh  .
RUN     chmod a+x fetch_example_programs.sh && ./fetch_example_programs.sh
RUN --mount=type=cache,target=/root/.cache/uv \
        uv sync --project /GDBMiner --frozen --no-dev

COPY    run_experiment.sh .
RUN     chmod a+x run_experiment.sh 


# Number of seeds to generate 
ENV     NUMBER_OF_SEEDS=20

#Whether we use the original mimid algorithm or our enhanced one
ENV     ORIGINAL_MIMID=0

#Whether we move watchpoints down the tree until we a new one occurs
ENV     DELAY_WP=0

#Number of inputs to sample for calculating precision and recall values
ENV     PRECISION_SET_SIZE=1000
