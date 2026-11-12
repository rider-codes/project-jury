"""Run the API: python -m jury.api [--port 8000] [--demo-model]

--demo-model (or JURY_DEMO_MODEL=1) uses a free offline stand-in model, for UI work.
"""

import argparse
import os

import uvicorn
from dotenv import load_dotenv

from jury.api.app import create_app
from jury.api.demo_llm import DemoLLM
from jury.llm import LLM


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default=os.environ.get("HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", 8000)))
    parser.add_argument("--db", default=os.environ.get("JURY_DB", "jury.sqlite"))
    parser.add_argument("--demo-model", action="store_true")
    args = parser.parse_args()
    load_dotenv()

    demo = args.demo_model or os.environ.get("JURY_DEMO_MODEL") == "1"
    if demo:
        print("Using the DEMO model: free and offline, opinions are canned.")
        factory = DemoLLM
    else:
        LLM.from_env()  # fail fast on a missing key
        factory = LLM.from_env
    if args.host not in ("127.0.0.1", "localhost") and not os.environ.get("JURY_ACCESS_CODE") and not demo:
        print("WARNING: serving publicly with real models and no JURY_ACCESS_CODE: anyone can spend your quota.")
    uvicorn.run(create_app(args.db, factory), host=args.host, port=args.port, proxy_headers=True,
                forwarded_allow_ips="*")


if __name__ == "__main__":
    main()
