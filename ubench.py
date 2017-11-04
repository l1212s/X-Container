import argparse
import util

class Benchmark(object):
  def run(self):
    raise "run: Not implemented"

  def parse(self):
    raise "parse: Not implemented"  


class CpuBenchmark(Benchmark):
  def __init__(self):
    super().__init__()
    self.duration = 60

  def run(self): 
    util.shell_call('XcontainerBolt/uBench/src/cpu {0:d}'.format(self.duration))


class MemoryBandwidthBenchmark(Benchmark):
  def __init__(self):
    super().__init__()
    self.duration = 60
    self.intensity = 5

  def run(self): 
    util.shell_call('XcontainerBolt/uBench/src/memBw {0:d} {1:s}'.format(self.duration, self.intensity))


class MemoryCapacityBenchmark(Benchmark):
  def __init__(self):
    super().__init__()
    self.duration = 60
    self.intensity = 5

  def run(self): 
    util.shell_call('XcontainerBolt/uBench/src/memCap {0:d} {1:s}'.format(self.duration, self.intensity))


def parse_arguments():
  parser = argparse.ArgumentParser()
  parser.add_argument('-b', '--benchmark', help='Metric to benchmark (cpu, memory)')
  args = parser.parse_args()

  if args.benchmark == 'cpu':
    return CpuBenchmark()
  elif args.benchmark == 'memBw':
    return MemoryBandwidthBenchmark()
  elif args.benchmark == 'memCap':
    return MemoryCapacityBenchmark()
  else:
    raise Exception('parse_arguments: Not implemented')


def main():
  benchmark = parse_arguments()  
  benchmark.run()


if __name__ == '__main__':
  main()
