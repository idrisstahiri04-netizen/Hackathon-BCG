"""Live SMS conversation tests against a running backend (default http://127.0.0.1:8501).

Never edits backend source. Start a disposable backend first:
  DB_PATH=/tmp/conv_test/conv.db GATEWAY=sim uvicorn backend.app:app --port 8501
Run:  python -m backend.tests.conv.run_suite | run_flow | run_load | cost_estimate
"""
