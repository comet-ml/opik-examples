#!/usr/bin/env bash
# Run the distributed training demo on the box provisioned by this folder's terraform.
#
#   ./run_remote_training.sh <host> [--epochs N] [--project NAME] [--branch REF] [--peak-tflops X]
#
# <host> is the public DNS/IP from `terraform output` (login user is ubuntu, so pass
# either `ubuntu@<dns>` or just `<dns>`). Credentials come from ../.env (or the ambient
# environment) and travel to the box over stdin into a chmod-600 file - never through
# the remote command line, where they would be visible to `ps`.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -f "${SCRIPT_DIR}/../.env" ]]; then
    set -a
    # shellcheck source=/dev/null
    source "${SCRIPT_DIR}/../.env"
    set +a
fi

usage() { grep '^#' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; }

host="${1:-}"
[[ -n "$host" ]] || { usage; exit 1; }
shift

epochs=2
project="${COMET_PROJECT_NAME:-capacity-demo-training}"
branch="main"
peak_tflops=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --epochs) epochs="$2"; shift 2 ;;
        --project) project="$2"; shift 2 ;;
        --branch) branch="$2"; shift 2 ;;
        --peak-tflops) peak_tflops="$2"; shift 2 ;;
        *) usage; exit 1 ;;
    esac
done

# These values are interpolated into a remote shell - keep them boring.
[[ "$epochs" =~ ^[0-9]+$ ]] || { echo "--epochs must be an integer" >&2; exit 1; }
[[ "$project" =~ ^[A-Za-z0-9._-]+$ ]] || { echo "--project has unexpected characters" >&2; exit 1; }
[[ "$branch" =~ ^[A-Za-z0-9._/-]+$ ]] || { echo "--branch has unexpected characters" >&2; exit 1; }
[[ -z "$peak_tflops" || "$peak_tflops" =~ ^[0-9]+([.][0-9]+)?$ ]] \
    || { echo "--peak-tflops must be a number" >&2; exit 1; }

if [[ -z "${COMET_API_KEY:-}" ]]; then
    echo "COMET_API_KEY is not set - fill in ../.env (see ../.env.example)." >&2
    exit 1
fi
[[ "$host" == *@* ]] || host="ubuntu@${host}"
SSH_OPTS=(-o StrictHostKeyChecking=accept-new)

echo "==> Shipping Comet credentials to ${host} (stdin -> chmod 600 file)"
{
    printf 'COMET_API_KEY=%s\n' "$COMET_API_KEY"
    [[ -n "${COMET_WORKSPACE:-}" ]] && printf 'COMET_WORKSPACE=%s\n' "$COMET_WORKSPACE"
    [[ -n "${COMET_URL_OVERRIDE:-}" ]] && printf 'COMET_URL_OVERRIDE=%s\n' "$COMET_URL_OVERRIDE"
    true
} | ssh "${SSH_OPTS[@]}" "$host" 'umask 077; cat > ~/.capacity-training.env'

echo "==> Setup + training on ${host} (branch ${branch}, ${epochs} epochs, project ${project})"
ssh "${SSH_OPTS[@]}" "$host" bash -s -- "$branch" "$epochs" "$project" "$peak_tflops" <<'REMOTE'
set -euo pipefail
branch="$1"; epochs="$2"; project="$3"; peak_tflops="${4:-}"
trap 'rm -f ~/.capacity-training.env' EXIT

if ! command -v uv >/dev/null 2>&1 && [ ! -x "$HOME/.local/bin/uv" ]; then
    curl -LsSf https://astral.sh/uv/install.sh | sh
fi
export PATH="$HOME/.local/bin:$PATH"

if [ -d "$HOME/opik-examples/.git" ]; then
    git -C "$HOME/opik-examples" fetch origin "$branch"
    git -C "$HOME/opik-examples" checkout "$branch"
    git -C "$HOME/opik-examples" reset --hard "origin/$branch"
else
    git clone --branch "$branch" https://github.com/comet-ml/opik-examples.git "$HOME/opik-examples"
fi

cd "$HOME/opik-examples/guides/gpu_capacity_planning"
uv sync --extra train

set -a; . ~/.capacity-training.env; set +a
# The DL AMI's LD_LIBRARY_PATH points at the system CUDA/cuDNN, which shadows the newer
# cuDNN bundled in the pip torch wheels (CUDNN_STATUS_SUBLIBRARY_LOADING_FAILED).
unset LD_LIBRARY_PATH
gpus=$(nvidia-smi -L | wc -l)
extra_args=()
if [ -n "$peak_tflops" ]; then
    extra_args+=(--peak-tflops "$peak_tflops")
fi
echo "==> torchrun with ${gpus} GPU rank(s)"
uv run torchrun --nproc_per_node="$gpus" -m gpu_capacity_planning.train_demo \
    --epochs "$epochs" --project "$project" "${extra_args[@]}"
REMOTE

echo "==> Done. Next (local): uv run gpu-capacity-planning report --project ${project}"
