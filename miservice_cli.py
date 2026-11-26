#!/usr/bin/env python3
"""Windows exe entry point for MiService CLI.

Keeps the upstream CLI behaviour, but when launched by double-click with no
arguments it keeps the console window open so the usage text can be read.
"""

import sys

from miservice.__main__ import main


if __name__ == '__main__':
    # Upstream prints sys.argv[0] in every usage example; keep it short.
    sys.argv[0] = 'miservice.exe'
    main()
    # No arguments means the tool just printed usage. When double-clicked on
    # Windows the console would otherwise close immediately.
    if len(sys.argv) == 1:
        try:
            input('\n按回车键退出...')
        except (EOFError, KeyboardInterrupt):
            pass
