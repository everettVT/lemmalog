# Template: define the path variables below before use; local paths were removed.
#!/bin/sh
set -eu
unset LEMMALOG_AGENT_OPERATIONS
export LEMMALOG_DDLOG_WORKDIR=${RUNTIME_DIR}/builds
export LEMMALOG_DDLOG_BUILD=${RUNTIME_DIR}/build.sh
export DDLOG_HOME=${TOOLCHAIN_DIR}/ddlog
export DDLOG_CARGO=${TOOLCHAIN_DIR}/rustup/toolchains/1.65.0-aarch64-apple-darwin/bin/cargo
export DDLOG_CARGO_CONFIG=${TOOLCHAIN_DIR}/review_ddlog/.cargo/config.toml
export DDLOG_CARGO_LOCK=${PREPARED_BUILD_DIR}/Cargo.lock
export DDLOG_OFFLINE=1
export RUSTC=${TOOLCHAIN_DIR}/rustup/toolchains/1.65.0-aarch64-apple-darwin/bin/rustc
export CARGO_HOME=${TOOLCHAIN_DIR}/cargo-home
export CARGO_TARGET_DIR=${RUNTIME_DIR}/target
exec python3 ${CHECKOUT_DIR}/scripts/ddlog_dogfood.py --binary ${RUNTIME_DIR}/bin/lemmalog-ddlog-mcp --session ${RUNTIME_DIR}/baseline-session --actor codex-model-author "$@"
