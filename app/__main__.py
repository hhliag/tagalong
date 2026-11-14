import argparse

import uvicorn

from . import config, store

parser = argparse.ArgumentParser(prog="python -m app", description="Run the TagAlong demo.")
parser.add_argument("--reset", action="store_true",
                    help="reload saved data: forget label decisions and build progress")
args = parser.parse_args()

if args.reset:
    store.reset()
    print(f"Reset: cleared {config.STATE_DIR}")

print(f"TagAlong on http://localhost:{config.PORT}  (listening on {config.HOST}, data: {config.DATA_DIR})")
uvicorn.run("app.main:app", host=config.HOST, port=config.PORT,
            proxy_headers=True, forwarded_allow_ips="*")
