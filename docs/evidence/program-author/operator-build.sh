# Template: define the path variables below before use; local paths were removed.
#!/bin/sh
set -eu
if [ -f ${RUNTIME_DIR}/fail-next-build ]; then
    rm ${RUNTIME_DIR}/fail-next-build
    echo 'Operator-injected one-shot build failure for active-program preservation check' >&2
    exit 91
fi
exec ${CHECKOUT_DIR}/scripts/build-ddlog.sh "$@"
