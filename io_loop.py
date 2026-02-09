import os
import sys
import selectors
import errno

def start_io_loop(pty_fd):
    """
    Forwards data between Standard I/O and the PTY.
    """
    sel = selectors.DefaultSelector()

    # Register Standard Input (Keyboard) -> PTY
    sel.register(sys.stdin, selectors.EVENT_READ)

    # Register PTY Output -> Standard Output (Screen)
    sel.register(pty_fd, selectors.EVENT_READ)

    running = True
    while running:
        try:
            events = sel.select()
            for key, _ in events:
                try:
                    if key.fileobj == sys.stdin:
                        # User typed something
                        data = os.read(sys.stdin.fileno(), 1024)
                        if not data: # EOF (Ctrl+D)
                            running = False
                            break
                        os.write(pty_fd, data)

                    else:
                        # PTY outputted something
                        data = os.read(pty_fd, 1024)
                        if not data: # PTY closed
                            running = False
                            break
                        os.write(sys.stdout.fileno(), data)
                        sys.stdout.flush()

                except OSError as e:
                    if e.errno == errno.EIO:
                        # Input/Output error usually means PTY closed
                        running = False
                    else:
                        raise e

        except KeyboardInterrupt:
            # Pass Ctrl+C to PTY, don't kill Python script
            # In raw mode, the PTY handles the signal usually,
            # but this catches edge cases.
            pass
