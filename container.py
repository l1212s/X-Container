import argparse
import subprocess
import time
import util


class Memcached(object):
  port = 11211
  size = 512
  threads = 4

  def start_command(self, ip=None):
    addr = ''
    if ip is not None:
      addr = '-l {0:s}'.format(ip)
    return 'memcached -m {0:d} -u root -p {1:d} {2:s} -t {3:d}'.format(self.size, self.port, addr, self.threads)


class Container(object):
  def __init__(self, name, container, application, processor):
    self.application = application
    self.container = container
    self.name = name
    self.processor = processor

  def destroy(self):
    raise Exception('Container-destroy: Not implemented')

  def execute_command(self, command):
    raise Exception('Container-execute_command: Not implemented')

  def ip(self):
    raise Exception('Container-ip: Not implemented')

  def machine_ip(self):
    return util.get_ip_address('eno1')

  def setup(self):
    raise Exception('Container-setup: Not implemented')

  def start(self):
    raise Exception('Container-start: Not implemented')


class LinuxContainer(Container):
  def __init__(self, name, application, processor):
    Container.__init__(self, name, 'linux', application, processor)
    self.tmux_name = 'linux'

  def destroy(self):
    util.shell_call('tmux kill-session -t {0:s}'.format(self.tmux_name))
    util.shell_call('lxc-stop --name {0:s}'.format(self.name))
    util.shell_call('lxc-destroy --name {0:s}'.format(self.name))

  def execute_command(self, command):
    util.shell_call('lxc-attach --name {0:s} -- /bin/sh -c "{1:s}"'.format(self.name, command), True)

  def ip(self):
    try:
      output = util.shell_output('lxc-info -n {:s} -iH'.format(self.name)).decode('utf-8').strip()
      if output == "":
        return None
      return output
    except subprocess.CalledProcessError as e:
      return None

  def bridge_ip(self):
    return util.get_ip_address('lxcbr0')

  def start(self):
    util.shell_call('lxc-create --name {0:s} -t ubuntu'.format(self.name), True)
    util.shell_call('lxc-start --name {0:s} -d'.format(self.name), True)
    util.shell_call("lxc-cgroup -n {0:s} cpuset.cpus {1:d}".format(self.name, self.processor))
    util.shell_call('tmux new -s {0:s} -d'.format(self.tmux_name), True)
    # Need to sleep to let container establish network connection
    time.sleep(5)

  def setup(self):
    self.execute_command('apt-get update')


DOCKER_INSPECT_FILTER = "{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}"


class DockerContainer(Container):
  def __init__(self, name, application, processor):
    Container.__init__(self, name, 'docker', application, processor)

  def destroy(self):
    util.shell_call('docker stop {0:s}'.format(self.name))
    util.shell_call('docker rm {0:s}'.format(self.name))

  def execute_command(self, command):
    util.shell_call('docker exec -it {0:s} {1:s}'.format(self.name, command), True)

  def config(self):
    raise Exception("DockerContainer: config - not implemented")

  def ports(self):
    raise Exception("DockerContainer: ports - not implemented")

  def args(self):
    raise Exception("DockerContainer: args - not implemented")

  def ip(self):
    try:
      output = util.shell_output("docker inspect -f '{0:s}' {1:s}".format(DOCKER_INSPECT_FILTER, self.name))
      output = output.strip()
      if output == "":
        return None
      return output
    except subprocess.CalledProcessError as e:
      return None

  def bridge_ip(self):
    return util.get_ip_address('docker0')

  def start(self):
    # TODO: X-Container
    v = ''
    if self.config() != '':
      v = '-v {0:s}'.format(self.config())

    p = ''
    if self.ports() != '':
      p = '-p {0:s}'.format(self.ports())

    cpu = '-P --cpuset-cpus={0:d}'.format(self.processor)
    util.shell_call('docker run --name {0:s} {1:s} {2:s} {3:s} -d {4:s} {5:s}'.format(self.name, cpu, v, p, self.application, self.args()))
    time.sleep(5)

  def setup(self):
    # Do nothing
    return


class ApplicationContainer(Container):
  def setup_port_forwarding(self, machine_ip, machine_port, container_ip, container_port, bridge_ip):
    util.shell_call('iptables -I FORWARD -p tcp -d {0:s} -j ACCEPT'.format(container_ip))
    time.sleep(1)
    util.shell_call('iptables -I FORWARD -p tcp -s {0:s} -j ACCEPT'.format(container_ip))
    time.sleep(1)
    util.shell_call('iptables -I INPUT -m state --state NEW -p tcp -m multiport --dport {0:d} -s 0.0.0.0/0 -j ACCEPT'.format(machine_port))
    time.sleep(1)
    command = 'iptables -t nat -I PREROUTING --dst {0:s} -p tcp --dport {1:d} -j DNAT --to-destination {2:s}:{3:d}'
    util.shell_call(command.format(machine_ip, machine_port, container_ip, container_port))
    time.sleep(1)
    command = 'iptables -t nat -I POSTROUTING -p tcp --dst {0:s} --dport {1:d} -j SNAT --to-source {2:s}'
    util.shell_call(command.format(container_ip, container_port, bridge_ip))
    time.sleep(1)
    command = 'iptables -t nat -I OUTPUT --dst {0:s} -p tcp --dport {1:d} -j DNAT --to-destination {2:s}:{3:d}'
    util.shell_call(command.format(machine_ip, machine_port, container_ip, container_port))
    time.sleep(1)

  def benchmark_message(self):
    print("To benchmark run 'python docker_setup.py -c {0:s} -p {1:s}'".format(self.container, self.application))


class MemcachedDockerContainer(DockerContainer, ApplicationContainer, Memcached):
  def __init__(self, processor):
    DockerContainer.__init__(self, 'memcached_container', 'memcached', processor)

  def config(self):
    return ""

  def ports(self):
    return '0.0.0.0:{0:d}:{0:d}'.format(self.port)

  def args(self):
    return Memcached.start_command(self)

  def setup(self):
    DockerContainer.setup(self)
    ApplicationContainer.setup_port_forwarding(self, self.machine_ip(), self.port, self.ip(), self.port, self.bridge_ip())
    ApplicationContainer.benchmark_message(self)


class MemcachedLinuxContainer(LinuxContainer, ApplicationContainer, Memcached):
  def __init__(self, processor):
    LinuxContainer.__init__(self, 'memcached_container', 'memcached', processor)

  def setup(self):
    LinuxContainer.setup(self)
    LinuxContainer.execute_command(self, 'apt-get install -y memcached')
    # self.execute_command('/etc/init.d/memcached stop')
    # TODO: Do I need a config?
    # self.execute_command('sudo truncate -s0 /etc/memcached.conf')
    util.tmux_command(self.tmux_name, 'lxc-attach -n {0:s}'.format(self.name))
    time.sleep(1)
    util.tmux_command(self.tmux_name, Memcached.start_command(self, self.ip()))
    # util.shell_call("sudo lxc-cgroup -n {0:s} memory.limit_in_bytes 1G".format(self.name))
    util.shell_call("lxc-cgroup -n {0:s} cpuset.cpus {1:d}".format(self.name, self.processor))
    ApplicationContainer.setup_port_forwarding(self, self.machine_ip(), self.port, self.ip(), self.port, self.bridge_ip())
    ApplicationContainer.benchmark_message(self)


class BenchmarkContainer(Container):
  def __init__(self, metric, intensity, name, container, application, processor):
    Container.__init__(self, name, container, application, processor)
    self.metric = metric
    self.intensity = intensity
    self.duration = 7200
    self.tmux_name = 'benchmark'
    self.intensity = intensity

  def start(self):
    util.shell_call('tmux new -s {0:s} -d'.format(self.tmux_name))

  def setup(self):
    util.tmux_command(self.tmux_name, 'apt-get update')
    util.tmux_command(self.tmux_name, 'apt-get install -y git')
    util.tmux_command(self.tmux_name, 'apt-get install -y make')
    util.tmux_command(self.tmux_name, 'apt-get install -y g++')
    util.tmux_command(self.tmux_name, 'apt-get install -y ca-certificates')
    util.tmux_command(self.tmux_name, 'git clone https://github.coecis.cornell.edu/SAIL/XcontainerBolt.git')
    util.tmux_command(self.tmux_name, 'cd XcontainerBolt/uBench; make')
    time.sleep(60)

  def benchmark(self):
    args = ''
    if self.metric.startswith('mem'):
      args = '{0:d} {1:d}'.format(self.duration, self.intensity)
    elif self.metric.startswith('cpu'):
      args = '{0:d}'.format(self.duration)
    else:
      raise Exception('benchmark - not implemented')
    util.tmux_command(self.tmux_name, 'src/{0:s} {1:s}'.format(self.metric, args))

  def destroy(self):
    util.shell_call('tmux kill-session -t {0:s}'.format(self.tmux_name))


class BenchmarkLinuxContainer(LinuxContainer, BenchmarkContainer):
  def __init__(self, metric, intensity, application, processor):
    name = 'benchmark_linux_container'
    LinuxContainer.__init__(self, name, application, processor)
    BenchmarkContainer.__init__(self, metric, intensity, name, 'linux', application, processor)

  def setup(self):
    LinuxContainer.setup(self)
    BenchmarkContainer.setup(self)

  def destroy(self):
    LinuxContainer.destroy(self)
    BenchmarkContainer.destroy(self)


class BenchmarkDockerContainer(DockerContainer, BenchmarkContainer):
  def __init__(self, metric, intensity, application, processor):
    name = 'benchmark_docker_container'
    DockerContainer.__init__(self, name, 'bash', processor)
    BenchmarkContainer.__init__(self, metric, intensity, name, 'docker', application, processor)

  def setup(self):
    DockerContainer.setup(self)
    BenchmarkContainer.setup(self)

  def destroy(self):
    DockerContainer.destroy(self)
    BenchmarkContainer.destroy(self)

  def config(self):
    return ''

  def args(self):
    return ''

  def ports(self):
    return ''

  def start(self):
    BenchmarkContainer.start(self)
    util.tmux_command(self.tmux_name, 'docker run --name {0:s} --cpuset-cpus={1:d} -i ubuntu /bin/bash'.format(self.name, self.processor))


def get_benchmark_processor(test):
  if ('same-container' in test) or ('same-core' in test):
    return util.processor(0)
  elif ('different-logical-core' in test):
    return util.virtual_processor(0)
  elif ('different-core' in test):
    return util.processor(1)
  else:
    raise Exception('container.get_processor: Not implemented')


def parse_arguments():
  parser = argparse.ArgumentParser()
  parser.add_argument('-a', '--application', required=True, help='Application to benchmark')
  parser.add_argument('-c', '--container', required=True, help='Type of container to use')
  parser.add_argument('-d', '--destroy', action='store_true', default=False)
  parser.add_argument('-t', '--test', required=True, help='Benchmark Test to perform (run -t help to see list of tests)')

  args = parser.parse_args()
  util.check_benchmark(args)
  parts = args.test.split('-')
  metric = parts[0]
  if metric.startswith('mem'):
    intensity = int(parts[1])
  else:
    intensity = 0
  args.metric = metric
  args.intensity = intensity
  return args


def setup_containers(args):
  if 'same-container' in args.test:
    raise Exception('not implemented yet')
  else:
    p = get_benchmark_processor(args.test)
    if args.container == 'linux':
      m = MemcachedLinuxContainer(util.processor(0))
      b = BenchmarkLinuxContainer(args.metric, args.intensity, args.application, p)
    elif args.container == 'docker':
      m = MemcachedDockerContainer(util.processor(0))
      b = BenchmarkDockerContainer(args.metric, args.intensity, args.application, p)

    if args.destroy:
      m.destroy()
      b.destroy()
    else:
      m.start()
      m.setup()

      b.start()
      b.setup()
      b.benchmark()


def main():
  args = parse_arguments()
  setup_containers(args)


if __name__ == '__main__':
  main()
