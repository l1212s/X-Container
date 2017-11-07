import os
import subprocess

START_PROCESSOR = 18
START_VIRTUAL_PROCESSOR = 19


def shell_call(command, show_command=False):
  if show_command:
    print('RUNNING COMMAND: ' + command)
  p = subprocess.Popen(command, shell=True)
  p.wait()
  if show_command:
    print('')


def shell_output(command, show_command=False):
  if show_command:
    print('RUNNING COMMAND: ' + command)
  output = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE).communicate()[0]
  if show_command:
    print('')
  return output


def container_folder(process, container):
  return "benchmark/{0:s}-{1:s}".format(process, container)


def instance_folder(cf, date):
  return "{0:s}/{1:s}".format(cf, date)


def check_benchmark(args):
  benchmarks = [
    'cpu',
  ]

  for benchmark in ['memBw', 'memCap']:
    for i in [1, 5, 9]:
      benchmarks.append('{0:s}-{1:d}'.format(benchmark, i))

  benchmark_tests = [
    'bare'
  ]

  for benchmark in benchmarks:
    benchmark_tests.append('{0:s}-same-container'.format(benchmark))
    benchmark_tests.append('{0:s}-no-container-different-core'.format(benchmark))
    benchmark_tests.append('{0:s}-no-container-same-core'.format(benchmark))
    benchmark_tests.append('{0:s}-no-container-different-logical-core'.format(benchmark))
    benchmark_tests.append('{0:s}-different-container-same-core'.format(benchmark))
    benchmark_tests.append('{0:s}-different-container-different-logical-core'.format(benchmark))
    benchmark_tests.append('{0:s}-different-container-different-core'.format(benchmark))

  if args.test == 'help':
    print('Choose from the following:\n{0:s}'.format('\n'.join(benchmark_tests)))
    os.exit(0)
  elif args.test not in benchmark_tests:
    raise Exception('Invalid benchmark {0:s}. Choose from the following:\n{1:s}'.format(args.test, '\n'.join(benchmark_tests)))


def processor(i):
  return START_PROCESSOR + 2*i


def physical_processors(n):
  processors = []
  for i in range(n):
    processors.append(processor(i))
  return processors


def virtual_processor(i):
  return START_VIRTUAL_PROCESSOR + 2*i


def tmux_command(session, command):
  shell_call('tmux send -t {0:s} "{1:s}" C-m'.format(session, command))


def get_ip_address(name):
  return shell_output("/sbin/ifconfig {0:s} | grep 'inet addr:' | cut -d: -f2 | awk '{{ print $1 }}'".format(name)).strip()
