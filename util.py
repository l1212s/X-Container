import os
import subprocess

APPLICATION_CPU = 10  # (Bound to Core 10, Socket 0, NUMA 0)
APPLICATION_MEM = 0
LOGICAL_CPU = 22  # (Bound to Core 10, Socket 0, NUMA 0)
LOGICAL_MEM = 0
DIFFERENT_CPU = 11  # (Bound to Core 11, Socket 1, NUMA 1)
DIFFERENT_MEM = 1


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


def cpu(v='default'):
  if v == 'default':
    return APPLICATION_CPU
  elif v == 'logical':
    return LOGICAL_CPU
  elif v == 'different':
    return DIFFERENT_CPU
  else:
    raise Exception('cpu - not implemented')


def processor(i):
  return 18 + 2*i


def physical_processors(n):
  processors = []
  for i in range(n):
    processors.append(processor(i))
  return processors


def memory(v='default'):
  if v == 'default':
    return APPLICATION_MEM
  elif v == 'logical':
    return LOGICAL_MEM
  elif v == 'different':
    return DIFFERENT_MEM
  else:
    raise Exception('mem - not implemented')


def tmux_command(session, command, wait=False):
  prefix_wait_command = ''
  postfix_wait_command = ''
  if wait:
    prefix_wait_command = '; tmux wait-for -S command'
    postfix_wait_command = '\; wait-for command'
  shell_call('tmux send-keys -t {0:s} "{1:s}{2:s}" C-m{3:s}'.format(session, command, prefix_wait_command, postfix_wait_command))


def get_ip_address(name):
  return shell_output("/sbin/ifconfig {0:s} | grep 'inet addr:' | cut -d: -f2 | awk '{{ print $1 }}'".format(name)).strip()
