"""CLI for DUSN-X state/router training (compatible with existing smoke configs)."""
import argparse
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
for path in (REPO_ROOT / "python/src", REPO_ROOT / "python", REPO_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from dusnx_core.training import build_training_metadata, run_epoch, set_seed, train
from dusnx_core.dataset import FEEDBACK_CONTRACT_VERSION


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config",default="configs/smoke_v2.yaml")
    parser.add_argument("--data");parser.add_argument("--resume");parser.add_argument("--init-from")
    parser.add_argument("--epochs",type=int);parser.add_argument("--checkpoint")
    parser.add_argument("--device",choices=["auto","cpu","cuda"]);parser.add_argument("--smoke",action="store_true")
    args=parser.parse_args()
    train(args.config,data=args.data,resume=args.resume,init_from=args.init_from,epochs=args.epochs,
          checkpoint=args.checkpoint,device=args.device,smoke=args.smoke)


if __name__=="__main__":main()
