import signal
from winsize import set_pty_size

def setup_signals(pty_fd):
    def _handler(signum, frame):
        set_pty_size(pty_fd)

    # Trigger on window resize
    signal.signal(signal.SIGWINCH, _handler)
