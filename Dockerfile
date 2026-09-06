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
    build-essential openjdk-11-jdk-headless git patch \
    ninja-build pkg-config llvm-4.0 llvm-4.0-dev zlib1g-dev \
    libclang-8-dev clang-format-8 clang-8 clang-4.0 jq \
    autoconf automake libtool libjson-c-dev wget ca-certificates liblzma-dev \
    libreadline-gplv2-dev libncursesw5-dev libc6-dbg texinfo

RUN ln -s /usr/bin/clang-8 /usr/bin/clang && \
    ln -s /usr/bin/clang++-8 /usr/bin/clang++
ENV UV_PROJECT_ENVIRONMENT=/opt/gdbminer-venv \
    UV_PYTHON=3.9.17 \
    UV_CACHE_DIR=/root/.cache/uv \
    UV_LINK_MODE=copy \
    PATH="/opt/gdbminer-venv/bin:$PATH"
RUN     mkdir -p /GDBMiner /tmp/build
COPY    pyproject.toml uv.lock README.md LICENSE setup.py setup.cfg /GDBMiner/
RUN --mount=type=cache,target=/root/.cache/uv \
        uv sync --project /GDBMiner --frozen --no-dev --extra experiment --no-install-project

WORKDIR /tmp/build

RUN wget --retry-connrefused --waitretry=2 --tries=5 -O gdb-9.2.tar.gz \
        https://sourceware.org/pub/gdb/releases/gdb-9.2.tar.gz && \
    tar -xf gdb-9.2.tar.gz && cd gdb-9.2 && mkdir build && cd build && \
    ../configure --disable-gdbserver --disable-nls --disable-sim --with-python=no && \
    make -j"$(nproc)" && make install-strip && \
    rm -rf /tmp/build/*
    

RUN wget -O valgrind-3.21.0.tar.bz2 https://sourceware.org/pub/valgrind/valgrind-3.21.0.tar.bz2 && \
    tar -xf valgrind-3.21.0.tar.bz2 && cd valgrind-3.21.0 && \
    ./configure --enable-only64bit && make -j"$(nproc)" && make install-strip && \
    find /usr/local/libexec/valgrind -maxdepth 1 -type f -name '*-arm64-linux' \
        ! -name 'memcheck-arm64-linux' ! -name 'getoff-arm64-linux' -delete && \
    find /usr/local/libexec/valgrind -maxdepth 1 -type f -name 'vgpreload_*-arm64-linux.so' \
        ! -name 'vgpreload_core-arm64-linux.so' ! -name 'vgpreload_memcheck-arm64-linux.so' -delete && \
    rm -rf /usr/local/include/valgrind /usr/local/lib/valgrind /usr/local/share/doc/valgrind && \
    rm -rf /tmp/build/*

ARG JSON_C_COMMIT=ee9f67c81a3c2a44557f0cc16dc136c140293252
RUN mkdir json-c && \
    wget -O json-c.tar.gz "https://github.com/json-c/json-c/archive/${JSON_C_COMMIT}.tar.gz" && \
    tar -xf json-c.tar.gz --strip-components=1 -C json-c && \
    cd json-c && sh autogen.sh && ./configure && \
    make -j"$(nproc)" && make install-strip && \
    rm -rf /tmp/build/*

RUN git clone --depth 1 --single-branch https://github.com/vrthra/mimid.git /mimid && \
    cd /mimid && tar -xf taints.tar.gz && rm -rf .git taints.tar.gz && cd taints && \
    meson build/debug --prefix="$(pwd)/install" && \
    ninja -C build/debug install

RUN sed -i 's+pfuzzer=../../taints+pfuzzer=../taints+g' /mimid/Cmimid/Makefile


RUN git clone --branch master --single-branch --depth 1 https://github.com/neil-kulkarni/arvada.git /arvada && \
    rm -rf /arvada/.git

RUN git clone --branch master --single-branch --depth 1 https://github.com/rifatarefin/treevada /treevada && \
    rm -rf /treevada/.git

WORKDIR /

COPY    src /GDBMiner/src
COPY    example_programs /example_programs

COPY    fetch_example_programs.sh  .
ARG RUST_VERSION=1.85.1
RUN wget -qO /tmp/rustup-init https://sh.rustup.rs && \
    chmod +x /tmp/rustup-init fetch_example_programs.sh && \
    /tmp/rustup-init -y --profile minimal --default-toolchain "${RUST_VERSION}" && \
    PATH="/root/.cargo/bin:$PATH" ./fetch_example_programs.sh && \
    rm -rf /tmp/rustup-init /root/.cargo /root/.rustup && \
    sed -i '/\.cargo\/env/d' /root/.profile
RUN --mount=type=cache,target=/root/.cache/uv \
        uv sync --project /GDBMiner --frozen --no-dev --extra experiment

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

# Space-separated targets; override to run a smaller evaluation.
ENV     TARGETS="calc calcrs calccpp cgi_decode json jsonrs jsoncpp yxml xmlcpp mjs tinyc"
ENV     MIMID_TARGETS="calc cgi_decode json mjs tiny"
