import argparse
import functools
import os
import re
import subprocess
import threading
import time

NGINX_CONTAINER_NAME = "nginx_container"
NGINX_MACHINE_PORT = 80
NGINX_CONTAINER_PORT = 80
MEMCACHED_CONTAINER_NAME = "memcached_container"
MEMCACHED_MACHINE_PORT = 11101
MEMCACHED_CONTAINER_PORT = 11212
DOCKER_INSPECT_FILTER = "{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}"
XCONTAINER_INSPECT_FILTER = "{{.NetworkSettings.IPAddress}}"
PROCESSOR = 19
MEMCACHED_SIZE = 512


class myThread (threading.Thread):
  def __init__(self, threadId, name, fun):
    threading.Thread.__init__(self)
    self.threadId = threadId
    self.name = name
    self.fun = fun

  def run(self):
    self.fun()


def run_parallel_instances(fun):
  threads = []
  for i in range(len(fun)):
    thread = myThread(i, "thread-{0:d}".format(i), fun[i])
    thread.start()
    threads.append(thread)

  for t in threads:
    t.join()

#################################################################################################
# Common functionality
#################################################################################################


def shell_call(command, showCommand=False):
  if showCommand:
    print('RUNNING COMMAND: ' + command)
  p = subprocess.Popen(command, shell=True)
  p.wait()
  if showCommand:
    print('')


def shell_output(command, showCommand=False):
  if showCommand:
    print('RUNNING COMMAND: ' + command)
  output = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE).communicate()[0]
  if showCommand:
    print('')
  return output


def get_known_packages():
  output = shell_output('dpkg --get-selections').decode('utf-8')
  lines = output.split('\n')
  packages = list(map(lambda x: x.split('\t')[0], lines))
  packages = list(filter(lambda x: len(x) > 0, packages))
  return packages


def install(package, known_packages):
  if package in known_packages:
    print(package + " has already been installed")
  else:
    shell_call('apt-get install -y {0:s}'.format(package))


def install_common_dependencies(packages):
  shell_call('apt-get update')
  install('linux-tools-4.4.0-92-generic', packages)
  install('make', packages)
  install('gcc', packages)


def get_ip_address(name):
  return shell_output("/sbin/ifconfig {0:s} | grep 'inet addr:' | cut -d: -f2 | awk '{{ print $1 }}'".format(name)).strip()


def get_nginx_configuration():
  return '''
user  www-data;
worker_processes  1;

error_log  /var/log/nginx/error.log warn;
pid        /var/run/nginx.pid;

events {
    worker_connections  1024;
}

http {
    access_log  off;
    include       /etc/nginx/mime.types;
    default_type  application/octet-stream;

    sendfile        off; # disable to avoid caching and volume mount issues

    keepalive_timeout  120;

    include /etc/nginx/conf.d/*.conf;
}
'''


def get_memcached_configuration():
  return '''
# Run memcached as a daemon. This command is implied, and is not needed for the
# daemon to run. See the README.Debian that comes with this package for more
# information.
-d

# Start with a cap of 64 megs of memory. It's reasonable, and the daemon default
# Note that the daemon will grow to this size, but does not start out holding this much
# memory
-m {0:d}

# Default connection port is 11211
-p 11211
# Run the daemon as root. The start-memcached will default to running as root if no
# -u command is present in this config file
-u memcache

# Limit the number of simultaneous incoming connections. The daemon default is 1024
# -c 1024

# Lock down all paged memory. Consult with the README and homepage before you do this
# -k

# Return error when memory is exhausted (rather than removing items)
-M

# Maximize core file limit
# -r'''.format(MEMCACHED_SIZE)


def setup_nginx_configuration(configuration_file_path):
  f = open(configuration_file_path, 'w')
  f.write(get_nginx_configuration())
  f.close


def setup_memcached_configuration(configuration_file_path):
  f = open(configuration_file_path, 'w')
  f.write(get_memcached_configuration())
  f.close


def install_benchmark_dependencies(args):
  shell_call("mkdir benchmark")

  path = os.getcwd()
  packages = get_known_packages()

  if args.process == 'nginx':
    if not os.path.exists('wrk2'):
      shell_call('git clone https://github.com/sc2682cornell/wrk2.git')
    install('libssl-dev', packages)
    os.chdir('wrk2')
    shell_call('make')
  elif args.process == 'memcached':
    if not os.path.exists('XcontainerBolt'):
      shell_call('git clone https://github.coecis.cornell.edu/SAIL/XcontainerBolt.git')

    os.chdir('XcontainerBolt/mutated')
    shell_call('git submodule update --init')
    install('dh-autoreconf', packages)
    shell_call('./autogen.sh')
    shell_call('./configure')
    shell_call('make')

  os.chdir(path)


AVG_LATENCY = re.compile('.*Latency +([0-9\.a-z]+)')
TAIL_LATENCY = re.compile('.*99\.999% +([0-9\.a-z]+)')
THROUGHPUT = re.compile('.*Requests/sec: +([0-9\.]+)')


def parse_nginx_benchmark(file_name):
  f = open(file_name, "r")

  regex_exps = [AVG_LATENCY, TAIL_LATENCY, THROUGHPUT]
  results = ["N/A"] * 3

  for line in f.readlines():
    for i in range(len(regex_exps)):
      m = regex_exps[i].match(line)
      if m is not None:
        results[i] = m.group(1)
        break

  print(results)
  return results


NANOSECONDS_REGEX = re.compile("([0-9\.]+)us")
MILLISECONDS_REGEX = re.compile("([0-9\.]+)ms")
SECONDS_REGEX = re.compile("([0-9\.]+)s")
MINUTE_REGEX = re.compile("([0-9\.]+)m$")
NOT_AVAILABLE = re.compile("N/A")


def save_benchmark_results(instance_folder, file_names, results):
  files = map(lambda f: open("{0:s}/{1:s}.csv".format(instance_folder, f), "w+"), file_names)

  for result in results:
    rate = result[0]
    for i in range(len(files)):
      measurement = str(result[1][i])
      m = NOT_AVAILABLE.match(measurement)
      if m is not None:
        files[i].write("{0:d},N/A\n".format(rate))
        continue
      for regex in [(0.001, NANOSECONDS_REGEX), (1, MILLISECONDS_REGEX), (1000, SECONDS_REGEX), (60*1000, MINUTE_REGEX)]:
        print("measurement", measurement)
        m = regex[1].match(measurement)
        if m is not None:
          measurement = m.group(1)
          try:
            measurement = float(measurement) * regex[0]
          except Exception:
            print("exception")
        break

      try:
        fmeasurement = float(measurement)
        if measurement == str(fmeasurement):
          files[i].write("{0:f},{1:d},{2:0.2f}\n".format(float(rate), core, fmeasurement))
        else:
          files[i].write("{0:f},{1:d},{2:s}\n".format(float(rate), core, str(measurement)))
      except Exception:
        files[i].write("{0:f},{1:d},{2:s}\n".format(float(rate), core, str(measurement)))


def get_rates(args, num_connections):
  if args.process == "nginx":
    rates = range(5, 500, 5)
  elif args.process == "memcached":
    rates = range(10000, 200000, 10000)
  else:
    raise "get_rates: not implemented"
  return rates


def get_date():
  return shell_output('date +%F-%H-%M-%S').strip()


def create_benchmark_folder(date, process, container):
  nginx_folder = "benchmark/{0:s}-{1:s}".format(process, container)
  shell_call("mkdir {0:s}".format(nginx_folder))
  instance_folder = "{0:s}/{1:s}".format(nginx_folder, date)
  shell_call("mkdir {0:1}".format(instance_folder))
  return instance_folder


def run_nginx_benchmark(args, num_connections, num_threads, duration):
  instance_folder = create_benchmark_folder(args.date, args.process, args.container)
  print("Putting NGINX benchmarks in {0:s}".format(instance_folder))

  rates = get_rates(args, num_connections)
  results = []
  for rate in rates:
    rate = rate * num_connections
    benchmark_file = "{0:s}/r{1:d}-t{2:d}-c{3:d}-d{4:d}".format(instance_folder, rate, num_threads, num_connections, duration)
    shell_call('XcontainerBolt/wrk2/wrk -R{0:d} -t{1:d} -c{2:d} -d{3:d}s -L http://{4:s} > {5:s}'
               .format(rate, num_threads, num_connections, duration, args.benchmark_address, benchmark_file), True)
    results.append((rate, parse_nginx_benchmark(benchmark_file)))

  result_files = ["avg_latency", "tail_latency", "throughput"]
  save_benchmark_results(instance_folder, result_files, results)


STATS = re.compile("([0-9]+)\t([0-9\.]+)\t([0-9\.]+)\t([0-9\.]+)\t([0-9\.]+)\t([0-9\.]+)")
BUFFER = re.compile("([RT][X]): ([0-9\.]+ [A-Za-z\/]+) \(([0-9\.]+ [A-Za-z\/]+)\)")
MISSED_SENDS = re.compile("Missed sends: ([0-9]+) / ([0-9]+) \(([0-9\.%]+)\)")
MUTATED_FOLDER = 'XcontainerBolt/mutated/client/'
NUM_MEMCACHED_KEYS = 10*1024
MEMCACHED_VALUE_SIZE = 200


def parse_memcached_benchmark(file_name):
  f = open(file_name, "r")
  lines = f.readlines()

  [throughput, rate] = lines[1].strip().split('\t')

  m = STATS.match(lines[4].strip())
  avg_rtt = float(m.group(2))
  tail_rtt = float(m.group(5))

  m = STATS.match(lines[7].strip())
  avg_load_generator_queue = m.group(2)
  tail_load_generator_queue = m.group(5)

  m = BUFFER.match(lines[9].strip())
  receive = m.group(2)
  m = BUFFER.match(lines[10].strip())
  transmit = m.group(2)

  m = MISSED_SENDS.match(lines[11].strip())
  missed_sends = m.group(3)

  results = (float(throughput), avg_rtt, tail_rtt, avg_load_generator_queue, tail_load_generator_queue, receive, transmit, missed_sends)
  return results


def get_memcached_benchmark_file(instance_folder, rate, num_connections, core):
  return "{0:s}/r{1:d}-c{2:d}-k{3:d}-v{4:d}-core{5:d}".format(instance_folder, rate, num_connections, NUM_MEMCACHED_KEYS, MEMCACHED_VALUE_SIZE, core)


def parse_memcached_results(args, instance_folder, num_connections, cores):
  rates = get_rates(args, num_connections)
  file_names = ["throughput", "avg_rtt", "tail_rtt"]
  files = map(lambda f: open("{0:s}/{1:s}.csv".format(instance_folder, f), "w+"), file_names)

  for rate in rates:
    sums = map(lambda f: 0.0, file_names)
    for core in cores:
      benchmark_file = get_memcached_benchmark_file(instance_folder, rate, num_connections, core)
      core_results = parse_memcached_benchmark(benchmark_file)
      for i in range(len(sums)):
        sums[i] += core_results[i]
    files[0].write("{0:f},{1:d}\n".format(sums[0], rate))
    for i in range(1, len(files)):
      files[i].write("{0:f},{1:f}\n".format(sums[0], sums[i]))

  for f in files:
    f.close()


def memcached_benchmark(results, instance_folder, num_connections, address, rate, core):
  benchmark_file = get_memcached_benchmark_file(instance_folder, rate, num_connections, core)
  command = 'taskset -c {0:d} {1:s}mutated_memcache -z {2:d} -v {3:d} -n {4:d} -W 10000 {5:s} {6:d} > {7:s}'
  shell_call(command.format(core, MUTATED_FOLDER, NUM_MEMCACHED_KEYS, MEMCACHED_VALUE_SIZE, num_connections, args.benchmark_address, rate, benchmark_file), True)


def run_memcached_benchmark(args):
  num_connections = args.connections / args.cores

  instance_folder = create_benchmark_folder(args.date, args.process, args.container)
  print("Putting Memcached benchmarks in {0:s}".format(instance_folder))

  shell_call('{0:s}load_memcache -z {1:d} -v {2:d} {3:s}'.format(MUTATED_FOLDER, NUM_MEMCACHED_KEYS, MEMCACHED_VALUE_SIZE, args.benchmark_address))

  rates = get_rates(args, num_connections)
  results = []
  cores = []
  for i in range(args.cores):
    cores.append(PROCESSOR + i)

  for rate in rates:
    break
    mem_funs = []
    for i in range(args.cores):
      mem_funs.append(functools.partial(memcached_benchmark, results, instance_folder, num_connections, args.benchmark_address, rate, PROCESSOR + i))
    run_parallel_instances(mem_funs)
  parse_memcached_results(args, instance_folder, num_connections, cores)


def run_benchmarks(args):
  install_benchmark_dependencies(args)
  if args.process == "nginx":
    run_nginx_benchmark(args, args.connections, args.threads, args.duration)
  elif args.process == "memcached":
    run_memcached_benchmark(args)


def destroy_container(args):
  if args.container == "docker":
    destroy_docker(args)
  elif args.container == "linux":
    destroy_linux(args)
  elif args.container == "xcontainer":
    destroy_xcontainer(args)
  else:
    raise "destroy_container: Not implemented"


def setup(args):
  if args.container == "docker":
    setup_docker(args)
  elif args.container == "linux":
    setup_linux(args)
  elif args.container == "xcontainer":
    setup_xcontainer(args)
  else:
    raise "setup: Not implemented for container " + args.container


def setup_port_forwarding(machine_ip, machine_port, container_ip, container_port, bridge_ip):
  shell_call('iptables -I FORWARD -p tcp -d {0:s} -j ACCEPT'.format(container_ip))
  linux_sleep(1)
  shell_call('iptables -I FORWARD -p tcp -s {0:s} -j ACCEPT'.format(container_ip))
  linux_sleep(1)
  shell_call('iptables -I INPUT -m state --state NEW -p tcp -m multiport --dport {0:d} -s 0.0.0.0/0 -j ACCEPT'.format(machine_port))
  linux_sleep(1)
  command = 'iptables -t nat -I PREROUTING --dst {0:s} -p tcp --dport {1:d} -j DNAT --to-destination {2:s}:{3:d}'
  shell_call(command.format(machine_ip, machine_port, container_ip, container_port))
  linux_sleep(1)
  command = 'iptables -t nat -I POSTROUTING -p tcp --dst {0:s} --dport {1:d} -j SNAT --to-source {2:s}'
  shell_call(command.format(container_ip, container_port, bridge_ip))
  linux_sleep(1)
  command = 'iptables -t nat -I OUTPUT --dst {0:s} -p tcp --dport {1:d} -j DNAT --to-destination {2:s}:{3:d}'
  shell_call(command.format(machine_ip, machine_port, container_ip, container_port))
  linux_sleep(1)


#################################################################################################
# X-container specific specific
#################################################################################################
def generate_xcontainer_ip(bridge_ip):
  parts = bridge_ip.split(".")
  last = int(parts[-1])
  new_last = (last + 1) % 255
  parts[-1] = str(new_last)
  return ".".join(parts)


def setup_xcontainer(args):
  if args.process == "nginx":
    name = NGINX_CONTAINER_NAME
    container_port = NGINX_CONTAINER_PORT
    machine_port = NGINX_MACHINE_PORT
    create_docker_nginx_container(args, XCONTAINER_INSPECT_FILTER, True)
  elif args.process == "memcached":
    name = MEMCACHED_CONTAINER_NAME
    container_port = MEMCACHED_CONTAINER_PORT
    machine_port = MEMCACHED_MACHINE_PORT
  else:
    raise Exception("setup_xcontainer: not implemented")

  bridge_ip = get_ip_address('xenbr0')
  docker_id = shell_output('docker inspect --format="{{{{.Id}}}}" {0:s}'.format(name)).strip()
  bridge_ip = get_ip_address('xenbr0')
  xcontainer_ip = generate_xcontainer_ip(bridge_ip)
  shell_call('docker stop {0:s}'.format(name))
  os.chdir('/root/experiments/native/compute06/docker')
  machine_ip = get_ip_address('em1')
  setup_port_forwarding(machine_ip, machine_port, xcontainer_ip, container_port, bridge_ip)
  print('Setup {0:s} X-Container on {1:s}:{1:2}'.format(args.process, machine_ip, machine_port))
  print('X-Container will take over this terminal....')
  shell_call('python run.py --id {0:s} --ip {1:s} --hvm --name {2:s} --cpu={3:d}'.format(docker_id, xcontainer_ip, name, args.cores))


def destroy_xcontainer_container(name):
  shell_call("xl destroy {0:s}".format(name))
  shell_call("docker rm {0:s}".format(name))


def destroy_xcontainer(args):
  if args.process == "nginx":
    destroy_xcontainer_container(NGINX_CONTAINER_NAME)
  elif args.process == "memcached":
    destroy_xcontainer_container(MEMCACHED_CONTAINER_NAME)


#################################################################################################
# Docker specific
#################################################################################################
def install_docker_dependencies():
  packages = get_known_packages()
  install_common_dependencies(packages)

  # apt-get may not know about about docker
  if 'docker-ce' in packages:
    print('docker-ce has already been installed')
  else:
    shell_call('curl -fsSL https://download.docker.com/linux/ubuntu/gpg | apt-key add -')
    shell_call('add-apt-repository "deb [arch=amd64] https://download.docker.com/linux/ubuntu xenial stable"')
    shell_call('apt-get update')
    shell_call('apt-get install -y docker-ce')

  if args.benchmark_address == 'benchmark':
    if args.process == 'nginx':
      if not os.path.exists('wrk'):
        shell_call('git clone https://github.com/wg/wrk.git')
        shell_call('make -j4 -C wrk')
    elif args.process == 'memcached':
      if not os.path.exists('XcontainerBolt'):
        shell_call('git clone https://github.coecis.cornell.edu/SAIL/XcontainerBolt.git')
        path = os.getcwd()
        os.chdir('XcontainerBolt')
        shell_call('git submodule update --init')
        os.chdir('mutated')
        install('dh-autoreconf', packages)
        shell_call('./autogen.sh')
        shell_call('./configure')
        shell_call('make')
        os.chdir(path)


def destroy_docker_container(name):
  shell_call('docker stop ' + name)
  shell_call('docker rm ' + name)


def nginx_docker_port():
  return docker_port(NGINX_CONTAINER_NAME, '([0-9]+)/tcp -> 0.0.0.0:([0-9]+)')


def memcached_docker_port():
  return docker_port(MEMCACHED_CONTAINER_NAME, '([0-9]+)/tcp -> 0.0.0.0:([0-9]+)')


def create_docker_nginx_container(args, docker_filter, is_xcontainer=False):
  configuration_file_path = '/dev/nginx.conf'
  setup_nginx_configuration(configuration_file_path)

  print(NGINX_CONTAINER_NAME, docker_filter)
  address = docker_ip(NGINX_CONTAINER_NAME, docker_filter)
  if args.cores > 1:
    raise "multi-core not implemented"
  cpu = "--cpuset-cpus={0:d}".format(PROCESSOR)
  if is_xcontainer:
    cpu = ""
  if address is None:
    command = 'docker run --name {0:s} -P {1:s} -v {2:s}:/etc/nginx/nginx.conf:ro -d nginx'
    shell_call(command.format(NGINX_CONTAINER_NAME, cpu, configuration_file_path))
    linux_sleep(5)
    address = docker_ip(NGINX_CONTAINER_NAME, docker_filter)
  ports = nginx_docker_port()
  machine_ip = get_ip_address('eno1')
  bridge_ip = get_ip_address('docker0')
  setup_port_forwarding(machine_ip, int(ports[1]), address, int(ports[0]), bridge_ip)
  print("To benchmark run 'python docker_setup.py -c docker -p nginx -b {0:s}:{1:s}'".format(machine_ip, ports[1]))
  return ports


def check_processor(args, name):
  if args.container == "docker":
    print("here")
    command = "sudo docker inspect -f '{{{{.HostConfig.CpusetCpus}}}}' {0:s}".format(name)
    print(command)
    output = shell_output(command).strip()
    print(output)
  elif args.container == "linux":
    output = shell_output("lxc-cgroup -n {0:s} cpuset.cpus".format(name)).strip()
  else:
    raise Exception("check_processor: Not implemented")
  print(output)
  if output != str(PROCESSOR):
    raise Exception("Error. Container is not bound to processor {0:d}".format(PROCESSOR))


def setup_docker_memcached_container(args, docker_filter, is_xcontainer=False):
  address = docker_ip(MEMCACHED_CONTAINER_NAME, docker_filter)
  configuration_file_path = '/dev/memcached.conf'
  setup_memcached_configuration(configuration_file_path)

  address = docker_ip(MEMCACHED_CONTAINER_NAME, docker_filter)
  if args.cores > 1:
    raise "multi-core not implemented"
  cpu = "--cpuset-cpus={0:d}".format(PROCESSOR)
  if is_xcontainer:
    cpu = ""

  if address is None:
    # TODO: Way to pass in memcached parameters like memory size
    shell_call('docker run --name {0:s} -P {1:s} -p 0.0.0.0:{2:d}:{3:d} -d memcached -m {4:d}'
               .format(MEMCACHED_CONTAINER_NAME, cpu, MEMCACHED_MACHINE_PORT, MEMCACHED_CONTAINER_PORT, MEMCACHED_SIZE)
               )
    address = docker_ip(MEMCACHED_CONTAINER_NAME, docker_filter)
  else:
    shell_call('docker start --name {0:s}'.format(MEMCACHED_CONTAINER_NAME))

  check_processor(args, MEMCACHED_CONTAINER_NAME)
  ports = memcached_docker_port()
  machine_ip = get_ip_address('eno1')
  bridge_ip = get_ip_address('docker0')
  setup_port_forwarding(machine_ip, int(ports[1]), address, int(ports[0]), bridge_ip)
  print("To benchmark run 'python docker_setup.py -c docker -p memcached -b {0:s}:{1:s}'".format(machine_ip, ports[1]))
  return ports


def docker_port(name, regex):
  try:
    output = shell_output('docker port {0:s}'.format(name))
    results = re.findall(regex, output)
    if len(results) == 0:
      return None
    else:
      return list(results[0])
  except subprocess.CalledProcessError as e:
    return None


def docker_ip(name, docker_filter):
  print(docker_filter, name)
  try:
    output = shell_output("docker inspect -f '{0:s}' {1:s}".format(docker_filter, name))
    output = output.strip()
    if output == "":
      return None
    return output
  except subprocess.CalledProcessError as e:
    return None


def setup_docker(args):
  install_docker_dependencies()
  if args.process == "nginx":
    create_docker_nginx_container(args, DOCKER_INSPECT_FILTER)
  elif args.process == "memcached":
    setup_docker_memcached_container(args, DOCKER_INSPECT_FILTER)


def destroy_docker(args):
  if args.process == "nginx":
    destroy_docker_container(NGINX_CONTAINER_NAME)
  elif args.process == "memcached":
    destroy_docker_container(MEMCACHED_CONTAINER_NAME)


#################################################################################################
# Linux specific
#################################################################################################

def install_linux_dependencies():
  packages = get_known_packages()
  install_common_dependencies(packages)

  if 'lxc' in packages:
    print('lxc has already been installed')
  else:
    install('lxc', packages)


def linux_container_execute_command(name, command):
  c = 'lxc-attach --name ' + name + ' -- /bin/sh -c "' + command + '"'
  print(c)
  shell_call('lxc-attach --name ' + name + ' -- /bin/sh -c "' + command + '"')


def get_linux_container_ip(name):
  try:
    output = shell_output('lxc-info -n {:s} -iH'.format(name))
    output = output.decode('utf-8').strip()
    if output == "":
      return None
    return output
  except subprocess.CalledProcessError as e:
    return None


def setup_linux(args):
  install_linux_dependencies()
  if args.process == "nginx":
    name = NGINX_CONTAINER_NAME
    container_ip = get_linux_container_ip(name)
    container_port = NGINX_CONTAINER_PORT
    machine_port = NGINX_MACHINE_PORT
    if container_ip is None:
      setup_linux_nginx_container()
  elif args.process == "memcached":
    name = MEMCACHED_CONTAINER_NAME
    container_ip = get_linux_container_ip(name)
    container_port = MEMCACHED_CONTAINER_PORT
    machine_port = MEMCACHED_MACHINE_PORT

    if container_ip is None:
      setup_linux_memcached_container()
      shell_call("sudo lxc-cgroup -n {0:s} memory.limit_in_bytes 1G".format(name))
  else:
    raise "setup_linux: Not implemented"

  container_ip = get_linux_container_ip(name)
  if args.cores > 1:
    raise Exception("Error need to implement logic for multiple cores")

  shell_call("sudo lxc-cgroup -n {0:s} cpuset.cpus {1:d}".format(name, PROCESSOR))
  check_processor(args, name)
  machine_ip = get_ip_address('eno1')
  bridge_ip = get_ip_address('lxcbr0')
  print("machine", machine_ip, machine_port, "container", container_ip, container_port, "bridge", bridge_ip)
  setup_port_forwarding(machine_ip, machine_port, container_ip, container_port, bridge_ip)
  print("To benchmark run 'python docker_setup.py -c linux -p {0:s} -b {1:s}:{2:d}'".format(args.process, machine_ip, machine_port))


def start_linux_container(name):
  # TODO: Is this the template we want?
  shell_call('lxc-create --name ' + name + ' -t ubuntu')
  shell_call('lxc-start --name ' + name + ' -d')


def linux_sleep(num_seconds):
  print("Sleeping for {0:d} seconds. Linux container network setup is slow....".format(num_seconds))
  time.sleep(num_seconds)


def setup_linux_nginx_container():
  start_linux_container(NGINX_CONTAINER_NAME)
  linux_sleep(5)
  linux_container_execute_command(NGINX_CONTAINER_NAME, 'sudo apt-get update')
  linux_container_execute_command(NGINX_CONTAINER_NAME, 'sudo apt-get install -y nginx')
#  linux_container_execute_command(NGINX_CONTAINER_NAME, 'systemctl status nginx')
  linux_container_execute_command(NGINX_CONTAINER_NAME, "sudo truncate -s0 /etc/nginx/nginx.config")

  for line in get_nginx_configuration().split("\n"):
    linux_container_execute_command(NGINX_CONTAINER_NAME, "sudo echo '{0:s}' >> /etc/nginx/nginx.config".format(line))
  linux_container_execute_command(NGINX_CONTAINER_NAME, '/etc/init.d/nginx restart')


def setup_linux_memcached_container():
  start_linux_container(MEMCACHED_CONTAINER_NAME)
  linux_sleep(5)
  linux_container_execute_command(MEMCACHED_CONTAINER_NAME, 'sudo apt-get update')
  linux_container_execute_command(MEMCACHED_CONTAINER_NAME, 'sudo apt-get install -y memcached')
  container_ip = get_linux_container_ip(MEMCACHED_CONTAINER_NAME)
  linux_container_execute_command(MEMCACHED_CONTAINER_NAME, '/etc/init.d/memcached stop')
  linux_container_execute_command(MEMCACHED_CONTAINER_NAME, "sudo truncate -s0 /etc/memcached.conf")
  for line in get_memcached_configuration().split("\n"):
    linux_container_execute_command(MEMCACHED_CONTAINER_NAME, "sudo echo '{0:s}' >> /etc/memcached.conf".format(line))
  command = 'memcached -m {0:d} -u root -p {1:d} -l {2:s} &'
  linux_container_execute_command(MEMCACHED_CONTAINER_NAME, command.format(MEMCACHED_SIZE, MEMCACHED_CONTAINER_PORT, container_ip))


def destroy_linux_container(name):
  shell_call('lxc-stop --name ' + name)
  shell_call('lxc-destroy --name ' + name)


def destroy_linux(args):
  if args.process == "nginx":
    destroy_linux_container(NGINX_CONTAINER_NAME)
  elif args.process == "memcached":
    destroy_linux_container(MEMCACHED_CONTAINER_NAME)

#################################################################################################
# Main
#################################################################################################


if __name__ == '__main__':
  # Example container setup
  # python3 docker_setup.py -c docker -p nginx

  # Example benchmark setup
  # python docker_setup.py -c docker -p nginx -b 1.2.3.4
  parser = argparse.ArgumentParser()
  parser.add_argument('-c', '--container', help='Indicate type of container (docker, linux)')
  parser.add_argument('-p', '--process', required=True, help='Indicate which process to run on docker (NGINX, Spark, etc)')
  parser.add_argument('-b', '--benchmark_address', type=str, help='Address and port to benchmark (localhost or 1.2.3.4:80)')
  parser.add_argument('-d', '--destroy', action='store_true', default=False, help='Destroy associated container')
  parser.add_argument('--cores', type=int, default=1, help='Number of cores')
  parser.add_argument('--duration', type=int, default=60, help='Benchmark duration')
  parser.add_argument('--connections', type=int, default=1, help='Number of client connections')
  parser.add_argument('--threads', type=int, default=1, help='Number of threads')
  parser.add_argument('--date', type=str, default=get_date(), help="Date folder to add benchmark results")
  args = parser.parse_args()
  args.connections = 100
  args.threads = 10

  if args.benchmark_address is not None:
    run_benchmarks(args)
  elif args.destroy:
    destroy_container(args)
  else:
    setup(args)
