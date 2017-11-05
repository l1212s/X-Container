import argparse
import util


class Benchmark(object):
  def __init__(self, benchmark, container):
    self.processor = self.get_processor(benchmark)
    self.container = container

  def get_processor(benchmark):
    if benchmark.contains('same-container') or benchmark.contains('same-core'):
      return util.processor(0)
    elif benchmark.contains('different-logical-core'):
      return util.virtual_processor(0)
    elif benchmark.contains('different-core'):
      return util.processor(1)
    else:
      raise Exception('Benchmark.get_processor: Not implemented')

  def run(self):
    raise "run: Not implemented"

  def parse(self):
    raise "parse: Not implemented"


class CpuBenchmark(Benchmark):
  def __init__(self):
    super().__init__()
    self.duration = 7200

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
  util.check_benchmark(args)

  if args.benchmark.startswith('cpu'):
    return CpuBenchmark()
  elif args.benchmark.startswith('memBw'):
    return MemoryBandwidthBenchmark()
  elif args.benchmark.startswith('memCap'):
    return MemoryCapacityBenchmark()
  else:
    raise Exception('parse_arguments: Not implemented')


def main():
  benchmark = parse_arguments()
  benchmark.run()


if __name__ == '__main__':
  main()
