import os
import fcntl
import struct
import termios
import sys

def set_pty_size(pty_fd):
    """
    Copies the window size (rows/cols) from the real terminal (stdin)
    to the PTY file descriptor.
    """
    try:
        # 1. Get size from REAL terminal (sys.stdout or sys.stdin)
        # We use struct.pack to create a buffer for the result
        result = fcntl.ioctl(sys.stdout.fileno(), termios.TIOCGWINSZ, b'\0'*8)

        # 2. Unpack (rows, cols, x_pixels, y_pixels)
        rows, cols, x_pix, y_pix = struct.unpack("HHHH", result)

        # 3. Apply to PTY
        # If cols is 0 (headless mode?), default to 80 to prevent crashes
        if cols == 0: cols = 80
        if rows == 0: rows = 24

        new_size = struct.pack("HHHH", rows, cols, x_pix, y_pix)
        fcntl.ioctl(pty_fd, termios.TIOCSWINSZ, new_size)

    except Exception:
        # Fallback if not running in a real terminal
        pass
