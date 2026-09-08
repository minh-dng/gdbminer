# syntax=docker/dockerfile:1.7
# This Dockerfile builds an image to run benchmark experiments in
# Copyright (c) 2023 Robert Bosch GmbH
# SPDX-License-Identifier: AGPL-3.0

FROM ubuntu:24.04
# Mimid's taint instrumentation was pinned to llvm-4.0, whose packages stopped
# shipping after ubuntu 18.04. The pass is ported to LLVM 14 via mimid-llvm14.patch,
# so the image builds on ubuntu 24.04 instead.

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

# ---------------------------------------------------------------------------
# Toolchain: mise manages version-pinned tools for linux/amd64 and linux/arm64
# (https://mise.jdx.dev, registry: https://mise-versions.jdx.dev).
# Single source for mise tools: docker/mise.toml (+ docker/mise.lock),
# installed below as the global mise config. Python is the exception: it is
# installed with uv (uv and Python releases are coupled), pinned by the
# repo-root .python-version shared with local development. The aqua backend
# selects the CPU architecture, so no TARGETARCH switch is needed. Native build
# dependencies remain on apt or source builds.
# ---------------------------------------------------------------------------
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt/lists,sharing=locked \
    rm -f /etc/apt/apt.conf.d/docker-clean \
    && echo 'Binary::apt::APT::Keep-Downloaded-Packages "true";' > /etc/apt/apt.conf.d/keep-cache \
    && apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install --no-install-recommends -y \
    build-essential git patch curl \
    pkg-config llvm-14-dev zlib1g-dev xz-utils \
    autoconf dh-autoreconf automake libtool libjson-c-dev \
    wget ca-certificates liblzma-dev libc6-dbg texinfo \
    libgmp-dev libmpfr-dev \
    clang-14 clang-format-14 libclang-14-dev

# Pin mise so image rebuilds do not silently change toolchain resolution.
# The image runs as root because its mise shims and installs live under /root.
ARG MISE_VERSION=2026.9.1
RUN curl -fsSL https://mise.run | MISE_VERSION=${MISE_VERSION} sh
# Keep /root/.local/bin in PATH because update-shell changes shell startup files,
# while Docker RUN commands use non-login shells.
ENV PATH="/opt/gdbminer-venv/bin:/root/.local/bin:/root/.local/share/mise/shims:$PATH" \
    MISE_YES=1

COPY docker/mise.toml /root/.config/mise/config.toml
COPY docker/mise.lock /root/.config/mise/mise.lock
COPY .python-version /GDBMiner/.python-version
# uv's --default flag is experimental. If it breaks in a future uv release,
# put Python back in docker/mise.toml and remove this uv Python installation.
RUN mise install --locked \
    && uv python install "$(cat /GDBMiner/.python-version)" --default \
    && uv python update-shell \
    && uv --version && python --version && UV_PYTHON=3.12 uv python find \
    && java -version && javac -version && cmake --version && ninja --version && jq --version \
    && ln -s "$(mise where java)" /opt/java \
    && /opt/java/bin/java -version && /opt/java/bin/javac -version \
    && rm -rf /root/.cache/mise

RUN ln -s /usr/bin/clang-14 /usr/bin/clang && \
    ln -s /usr/bin/clang++-14 /usr/bin/clang++ && \
    ln -s /usr/bin/llvm-config-14 /usr/local/bin/llvm-config
ENV JAVA_HOME=/opt/java \
    UV_PROJECT_ENVIRONMENT=/opt/gdbminer-venv \
    UV_PYTHON=3.12 \
    UV_CACHE_DIR=/root/.cache/uv \
    UV_LINK_MODE=copy
RUN     mkdir -p /GDBMiner /tmp/build
COPY    pyproject.toml uv.lock README.md LICENSE setup.py setup.cfg /GDBMiner/
RUN --mount=type=cache,target=/root/.cache/uv \
        uv sync --project /GDBMiner --frozen --no-dev --extra experiment --no-install-project

WORKDIR /tmp/build

RUN wget --retry-connrefused --waitretry=2 --tries=5 -O gdb-13.2.tar.gz \
        https://ftp.gnu.org/gnu/gdb/gdb-13.2.tar.gz && \
    tar -xf gdb-13.2.tar.gz && cd gdb-13.2 && mkdir build && cd build && \
    ../configure --disable-gdbserver --disable-nls --disable-sim --with-python=no && \
    make -j"$(nproc)" && make install-strip && \
    gdb --version && \
    rm -rf /tmp/build/*

RUN wget -O valgrind-3.23.0.tar.bz2 \
        https://ftp.osuosl.org/pub/blfs/conglomeration/valgrind/valgrind-3.23.0.tar.bz2 && \
    tar -xf valgrind-3.23.0.tar.bz2 && cd valgrind-3.23.0 && \
    ./configure --enable-only64bit && make -j"$(nproc)" && make install-strip && \
    valgrind --version && \
    vg_arch="$(dpkg --print-architecture)" && \
    find /usr/local/libexec/valgrind -maxdepth 1 -type f -name "*-${vg_arch}-linux" \
        ! -name "memcheck-${vg_arch}-linux" ! -name "getoff-${vg_arch}-linux" -delete && \
    find /usr/local/libexec/valgrind -maxdepth 1 -type f -name "vgpreload_*-${vg_arch}-linux.so" \
        ! -name "vgpreload_core-${vg_arch}-linux.so" ! -name "vgpreload_memcheck-${vg_arch}-linux.so" -delete && \
    rm -rf /usr/local/include/valgrind /usr/local/lib/valgrind /usr/local/share/doc/valgrind && \
    rm -rf /tmp/build/*

ARG JSON_C_COMMIT=ee9f67c81a3c2a44557f0cc16dc136c140293252
RUN mkdir json-c && \
    wget -O json-c.tar.gz "https://github.com/json-c/json-c/archive/${JSON_C_COMMIT}.tar.gz" && \
    tar -xf json-c.tar.gz --strip-components=1 -C json-c && \
    cd json-c && sh autogen.sh && ./configure && \
    make -j"$(nproc)" && make install-strip && \
    rm -rf /tmp/build/*

# Compile static libxml
RUN wget -O libxml2-2.12.4.tar.xz https://download.gnome.org/sources/libxml2/2.12/libxml2-2.12.4.tar.xz && \
    tar -xf libxml2-2.12.4.tar.xz && cd libxml2-2.12.4 && mkdir build && cd build && \
    cmake -D LIBXML2_WITH_ZLIB=OFF -D LIBXML2_WITH_LZMA=OFF -DLIBXML2_WITH_ICONV=OFF -DLIBXML2_WITH_THREADS=OFF -DBUILD_SHARED_LIBS=OFF -DCMAKE_BUILD_TYPE=Debug -DCMAKE_C_FLAGS="-O0" .. && \
    make -j"$(nproc)" && make install && ldconfig && \
    rm -rf /tmp/build/*

COPY    mimid-llvm14.patch /
# Pin the mimid checkout: mimid-llvm14.patch is written against these exact
# sources, and a moving master would break the patch non-reproducibly.
ARG MIMID_COMMIT=9c96909783ba99035372f78d6c52003f7f42b1ec
RUN git clone --depth 1 --single-branch https://github.com/vrthra/mimid.git /mimid && \
    git -C /mimid fetch --depth 1 origin "${MIMID_COMMIT}" && \
    git -C /mimid checkout --detach "${MIMID_COMMIT}" && \
    cd /mimid && tar -xf taints.tar.gz && patch -p1 < /mimid-llvm14.patch && \
    rm -rf .git taints.tar.gz /mimid-llvm14.patch && cd taints && \
    meson build/debug --prefix="$(pwd)/install" && \
    ninja -C build/debug install

RUN sed -i 's+pfuzzer=../../taints+pfuzzer=../taints+g' /mimid/Cmimid/Makefile && \
    sed -i 's+CC=clang-8+CC=clang-14+g' /mimid/Cmimid/Makefile && \
    sed -i "s+/usr/lib/llvm-8/lib/clang/8.0.0/include+$(clang-14 -print-resource-dir)+g" /mimid/Cmimid/Makefile && \
    sed -i 's+/usr/lib/llvm-8+/usr/lib/llvm-14+g' /mimid/Cmimid/Makefile


RUN git clone --branch master --single-branch --depth 1 https://github.com/neil-kulkarni/arvada.git /arvada && \
    rm -rf /arvada/.git

RUN git clone --branch master --single-branch --depth 1 https://github.com/rifatarefin/treevada /treevada && \
    rm -rf /treevada/.git

WORKDIR /

COPY    src /GDBMiner/src
COPY    example_programs /example_programs

COPY    fetch_example_programs.sh  .
RUN chmod +x fetch_example_programs.sh && \
    MISE_LOCKED=1 ./fetch_example_programs.sh && \
    mise uninstall rust && \
    rm -rf /root/.cargo /root/.rustup
RUN --mount=type=cache,target=/root/.cache/uv \
        uv sync --project /GDBMiner --frozen --no-dev --extra experiment

COPY    run_experiment.sh .
RUN     chmod a+x run_experiment.sh

COPY    scripts /scripts


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
