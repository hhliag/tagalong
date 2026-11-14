import argparse
import importlib
import os
import sys

from . import llm
from .common import PipelineError, out_dir

STAGES = ["pages", "extract", "handling", "label", "render"]


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m pipeline",
                                     description="Turn one chair folder into a labelled passport.")
    parser.add_argument("chair_id")
    parser.add_argument("--stage", choices=STAGES + ["all"], default="all")
    parser.add_argument("--provider", choices=llm.PROVIDERS,
                        default=os.environ.get("LLM_PROVIDER") or "offline")
    parser.add_argument("--model", default=os.environ.get("LLM_MODEL"))
    args = parser.parse_args(argv)

    llm.configure(args.provider, args.model, out_dir(args.chair_id))
    try:
        for stage in STAGES if args.stage == "all" else [args.stage]:
            importlib.import_module(f"pipeline.{stage}").run(args.chair_id)
    except llm.OfflineWaiting as e:
        print(f"Waiting for offline response: {e.path}")
        return 3
    except PipelineError as e:
        print(f"ERROR: {e}")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
