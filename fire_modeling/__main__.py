import sys
from .cli import main

# The command line is a UTF-8 JSON protocol even on Windows with a GBK locale.
for stream in (sys.stdout,sys.stderr):
    if hasattr(stream,'reconfigure'): stream.reconfigure(encoding='utf-8')

raise SystemExit(main())
