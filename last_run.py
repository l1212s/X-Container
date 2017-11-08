import argparse
import os
import re
import util

NUM_CLIENTS = re.compile('NUM CLIENTS: ([0-9]+)')
BENCHMARK_TEST = re.compile('BENCHMARK TEST: (.*)')

def correct_num_clients(output, expected_num_clients):
  m = re.search(NUM_CLIENTS, output)
  if m:
    actual_num_clients = int(m.group(1))
    return expected_num_clients == actual_num_clients
  else:
    return expected_num_clients == 1

def correct_benchmark(output, expected_benchmark):
  m = re.search(BENCHMARK_TEST, output)
  if m:
    return expected_benchmark == m.group(1)
  else:
    return expected_benchmark == 'bare'

def last_run(args):
  container_folder = util.container_folder(args.process, args.container)
  runs = util.shell_output('ls {0:s}'.format(container_folder)).strip().split('\n')
  runs.sort(reverse=True)

  i = 0
  for run in runs:
    readme_file = '{0:s}/{1:s}/README'.format(container_folder, run)
    if not os.path.isfile(readme_file):
      continue

    output = util.shell_output('cat {0:s}'.format(readme_file))
    if not correct_num_clients(output, args.num_clients):
      continue

    if not correct_benchmark(output, args.test):
      continue
    
    print(readme_file)    
    print(output)
    i += 1
    if i == args.instances:
      return

def parse_arguments():
  parser = argparse.ArgumentParser()
  parser.add_argument('-c', '--container', required=True, help='Container to find')
  parser.add_argument('-p', '--process', required=True, help='Application to find')
  parser.add_argument('-t', '--test', required=True, help='Test to find')
  parser.add_argument('-n', '--num_clients', type=int, default=1, help='Number of clients or cores to find')
  parser.add_argument('-i', '--instances', type=int, default=1, help='Number of runs to return')
  args = parser.parse_args()
  util.check_benchmark(args)
  return args

def main():
  args = parse_arguments()
  last_run(args)

if __name__ == '__main__':
  main()
