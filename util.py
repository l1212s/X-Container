import subprocess

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
    'cpu'
  ]

  benchmark_tests = [
    'bare'
  ]

  for benchmark in benchmarks:
    benchmark_tests.append('{0:s}-same-container'.format(benchmark))
    benchmark_tests.append('{0:s}-no-container-different-core'.format(benchmark))
    benchmark_tests.append('{0:s}-no-container-same-core'.format(benchmark))
    benchmark_tests.append('{0:s}-no-container-different-logical-core'.format(benchmark))
    benchmark_tests.append('{0:s}-different-container-same-logical-core'.format(benchmark))
    benchmark_tests.append('{0:s}-different-container-different-logical-core'.format(benchmark))
    benchmark_tests.append('{0:s}-different-container-different-physical-core'.format(benchmark))
 
  if args.benchmark not in benchmark_tests:
    raise Exception('Invalid benchmark {0:s}. Choose from the following:\n{1:s}'.format(args.benchmark, '\n'.join(benchmark_tests))) 
