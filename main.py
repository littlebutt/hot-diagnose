import sys

from engine.run import PyRunner
from engine.tracer import Tracer

if __name__ == '__main__':
    path = sys.argv[1]
    tracer = Tracer()
    tracer.start()
    runner = PyRunner(path, False)
    runner.run()
    tracer.stop()