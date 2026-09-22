"""Distributed demo training run that produces everything the capacity workflow consumes.

Launch (CPU works; on a GPU box the sys.gpu.* metrics appear automatically):

    uv sync --extra train
    uv run torchrun --nproc_per_node=2 -m gpu_capacity_planning.train_demo --epochs 2

Rank 0 logs one Comet EM experiment: hyperparameters (including world_size, which the
audit reads as declared scale), per-epoch loss/accuracy, final precision/recall/F1, and
system metrics (enabled explicitly below). The `report` command then closes the loop.

Optional efficiency extras (both per-model/per-hardware, hence opt-in):
- `--peak-tflops <per-GPU peak>` logs a per-epoch `mfu` metric (Model FLOPs Utilization).
- `--gpu-log-every N` logs `gpu.<i>.utilization`/`gpu.<i>.memory_pct` from inside the
  training loop with step+epoch attached, so the EM chart can plot them per step/epoch
  (the background `sys.gpu.*` sampler only supports a wall-time axis).
"""

import argparse
import os
import sys
import time

try:
    import comet_ml
    import torch
    import torch.distributed as dist
    import torch.nn as nn
    from sklearn.metrics import precision_recall_fscore_support
    from torch.nn.parallel import DistributedDataParallel
    from torch.utils.data import DataLoader
    from torch.utils.data.distributed import DistributedSampler
    from torchvision import datasets, transforms
except ImportError as exc:  # pragma: no cover
    sys.exit(f"Missing training dependency ({exc.name}). Install with: uv sync --extra train")

DATA_DIR = ".data-cache"


class SmallCNN(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.net = nn.Sequential(
            nn.Conv2d(1, 16, 3, padding=1),
            nn.ReLU(),
            nn.MaxPool2d(2),
            nn.Conv2d(16, 32, 3, padding=1),
            nn.ReLU(),
            nn.MaxPool2d(2),
            nn.Flatten(),
            nn.Linear(32 * 7 * 7, 10),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x)


def _distributed() -> tuple[int, int]:
    """(rank, world_size); initializes the process group when launched via torchrun."""
    world_size = int(os.environ.get("WORLD_SIZE", "1"))
    rank = int(os.environ.get("RANK", "0"))
    if world_size > 1 and not dist.is_initialized():
        dist.init_process_group("nccl" if torch.cuda.is_available() else "gloo")
    return rank, world_size


def _forward_flops_per_sample(model: nn.Module, batch: torch.Tensor, device: torch.device) -> float:
    """Measured forward FLOPs for one sample - architecture-specific, hence measured not assumed."""
    from torch.utils.flop_counter import FlopCounterMode

    counter = FlopCounterMode(display=False)
    with counter, torch.no_grad():
        model(batch.to(device))
    return counter.get_total_flops() / batch.shape[0]


def _nvml_handles() -> tuple:
    """(pynvml module, device handles) for in-loop GPU sampling; ([], None) when unavailable."""
    try:
        import pynvml

        pynvml.nvmlInit()
        handles = [pynvml.nvmlDeviceGetHandleByIndex(i) for i in range(pynvml.nvmlDeviceGetCount())]
        return pynvml, handles
    except Exception:  # noqa: BLE001 - no NVML (CPU box) is a normal, silent case
        return None, []


def _gpu_snapshot(pynvml, handles) -> dict[str, float]:
    metrics: dict[str, float] = {}
    for i, handle in enumerate(handles):
        rates = pynvml.nvmlDeviceGetUtilizationRates(handle)
        memory = pynvml.nvmlDeviceGetMemoryInfo(handle)
        metrics[f"gpu.{i}.utilization"] = rates.gpu
        metrics[f"gpu.{i}.memory_pct"] = round(100 * memory.used / memory.total, 1)
    return metrics


def _predict(model: nn.Module, test_loader: "DataLoader", device: torch.device) -> tuple[list, list]:
    model.eval()
    predictions, targets = [], []
    with torch.no_grad():
        for images, labels in test_loader:
            predictions.extend(model(images.to(device)).argmax(dim=1).cpu().tolist())
            targets.extend(labels.tolist())
    return predictions, targets


def _start_experiment(args: argparse.Namespace, world_size: int) -> "comet_ml.CometExperiment":
    experiment = comet_ml.start(
        project_name=args.project,
        experiment_config=comet_ml.ExperimentConfig(
            name=args.run_name,
            # Explicit so the run always carries the system metrics the audit reads,
            # even when a base config disabled them.
            log_env_details=True,
            log_env_gpu=True,
            log_env_cpu=True,
        ),
    )
    experiment.log_parameters(
        {
            "world_size": world_size,
            "epochs": args.epochs,
            "batch_size": args.batch_size,
            "lr": args.lr,
            "model": "small-cnn",
            "dataset": "fashion-mnist",
        }
    )
    return experiment


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--epochs", type=int, default=2)
    parser.add_argument("--batch-size", type=int, default=128)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--run-name", default=None)
    parser.add_argument("--project", default=os.environ.get("COMET_PROJECT_NAME", "capacity-demo-training"))
    parser.add_argument(
        "--peak-tflops",
        type=float,
        default=None,
        help="Per-GPU peak TFLOPS for the precision you train in (T4 fp32 ~8.1). "
        "Enables the per-epoch `mfu` metric; without it MFU is skipped - a made-up "
        "denominator would be worse than no number.",
    )
    parser.add_argument(
        "--gpu-log-every",
        type=int,
        default=10,
        help="Log per-GPU utilization/memory from inside the loop every N steps with "
        "step+epoch attached (0 disables). Complements the wall-clock sys.gpu.* sampler.",
    )
    args = parser.parse_args()

    if not os.environ.get("COMET_API_KEY"):
        sys.exit("COMET_API_KEY is not set - the training demo logs to a real Comet EM workspace.")

    rank, world_size = _distributed()
    # WHY: LOCAL_RANK indexes GPUs on this node; RANK is global and misindexes on multi-node.
    local_rank = int(os.environ.get("LOCAL_RANK", "0"))
    device = torch.device(f"cuda:{local_rank}" if torch.cuda.is_available() else "cpu")

    # Rank 0 downloads; the barrier keeps other ranks from racing the files.
    transform = transforms.ToTensor()
    if rank == 0:
        datasets.FashionMNIST(DATA_DIR, train=True, download=True)
        datasets.FashionMNIST(DATA_DIR, train=False, download=True)
    if world_size > 1:
        dist.barrier()
    train_set = datasets.FashionMNIST(DATA_DIR, train=True, transform=transform)
    test_set = datasets.FashionMNIST(DATA_DIR, train=False, transform=transform)

    sampler = DistributedSampler(train_set) if world_size > 1 else None
    train_loader = DataLoader(train_set, batch_size=args.batch_size, shuffle=sampler is None, sampler=sampler)
    test_loader = DataLoader(test_set, batch_size=512)

    model: nn.Module = SmallCNN().to(device)
    if world_size > 1:
        model = DistributedDataParallel(model)
    optimizer = torch.optim.Adam(model.parameters(), lr=args.lr)
    loss_fn = nn.CrossEntropyLoss()

    experiment = _start_experiment(args, world_size) if rank == 0 else None

    flops_per_sample = None
    if experiment and args.peak_tflops:
        sample_batch, _ = next(iter(train_loader))
        flops_per_sample = _forward_flops_per_sample(model, sample_batch, device)
        experiment.log_parameters(
            {"peak_tflops_per_gpu": args.peak_tflops, "flops_per_sample": flops_per_sample}
        )
    pynvml, nvml_handles = (None, [])
    if experiment and args.gpu_log_every > 0 and torch.cuda.is_available():
        pynvml, nvml_handles = _nvml_handles()

    global_step = 0
    for epoch in range(args.epochs):
        if sampler is not None:
            sampler.set_epoch(epoch)
        model.train()
        total_loss, batches = 0.0, 0
        epoch_start = time.perf_counter()
        for images, labels in train_loader:
            images, labels = images.to(device), labels.to(device)
            optimizer.zero_grad()
            loss = loss_fn(model(images), labels)
            loss.backward()
            optimizer.step()
            total_loss += loss.item()
            batches += 1
            global_step += 1
            if nvml_handles and global_step % args.gpu_log_every == 0:
                experiment.log_metrics(_gpu_snapshot(pynvml, nvml_handles), step=global_step, epoch=epoch)
        epoch_seconds = time.perf_counter() - epoch_start
        if experiment:
            predictions, targets = _predict(model, test_loader, device)
            accuracy = sum(p == t for p, t in zip(predictions, targets, strict=True)) / len(targets)
            epoch_metrics = {"loss": total_loss / max(batches, 1), "accuracy": accuracy}
            if flops_per_sample:
                # WHY: a training step costs ~3x a forward pass (forward + ~2x backward) -
                # a standard heuristic, so treat MFU as directional rather than exact.
                achieved = 3 * flops_per_sample * len(train_set) / epoch_seconds
                mfu = round(100 * achieved / (world_size * args.peak_tflops * 1e12), 2)
                epoch_metrics["mfu"] = mfu
                print(f"epoch {epoch}: mfu {mfu}%")
            experiment.log_metrics(epoch_metrics, step=global_step, epoch=epoch)

    if experiment:
        predictions, targets = _predict(model, test_loader, device)
        precision, recall, f1, _ = precision_recall_fscore_support(
            targets, predictions, average="macro", zero_division=0
        )
        accuracy = sum(p == t for p, t in zip(predictions, targets, strict=True)) / len(targets)
        experiment.log_metrics({"precision": precision, "recall": recall, "f1": f1, "accuracy": accuracy})
        experiment.end()
        print(f"\nExperiment: {experiment.url}")
        print(f"Experiment key: {experiment.get_key()}")

    if world_size > 1:
        dist.destroy_process_group()


if __name__ == "__main__":
    main()
