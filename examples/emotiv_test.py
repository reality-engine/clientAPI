import sys
import threading
import time
from datetime import datetime
from queue import Queue

from emotiv import QueryAPI


def main(key="basic", url="ws://localhost:8000/connect/text", debug=False):
    queue = Queue()

    q = QueryAPI(url, queue, debug)
    q.open()

    s = FakeSub(queue, debug)
    s.open()
    try:
        while True:
            input("Press Enter to generate AI...")
            result = q.trigger()
            print(result)
    except KeyboardInterrupt:
        print()
        s.close()
        q.close()


class FakeSub:
    def __init__(self, queue, debug=False):
        super().__init__()
        self.queue = queue
        self.debug = bool(debug)
        self._stopped = False

    def join(self):
        self.transmit_thread.join()

    def close(self):
        self._stopped = True

    def open(self):
        threadName = "TransmitThread:-{:%Y%m%d%H%M%S}".format(datetime.utcnow())
        self.transmit_thread = threading.Thread(
            target=self.handler, args=(), name=threadName
        )
        self.transmit_thread.start()

    def handler(self):
        while not self._stopped:
            self.queue.put({"Cx": 1.0, "Drm": 2.0})
            time.sleep(1 / 128)


if __name__ == "__main__":
    main(*sys.argv[1:])
