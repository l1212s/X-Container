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
  def __init__(self, name, container, application, processor_type):
    self.application = application
    self.container = container
    self.name = name
    self.processor = util.cpu(processor_type)
    self.mem = util.memory(processor_type)

  def name(self):
    return self.name

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
  def __init__(self, name, application, processor='default'):
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
    util.shell_call("lxc-cgroup -n {0:s} cpuset.cpus {1:d}".format(self.name, self.processor), True)
    util.shell_call("lxc-cgroup -n {0:s} cpuset.mems {1:d}".format(self.name, self.mem), True)
    util.shell_call('tmux new -s {0:s} -d'.format(self.tmux_name), True)
    # Need to sleep to let container establish network connection
    time.sleep(5)

  def setup(self):
    self.execute_command('apt-get update')


DOCKER_INSPECT_FILTER = "{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}"


class DockerContainer(Container):
  def __init__(self, name, application, processor='default'):
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

  def cpuset(self):
    return '-P --cpuset-cpus={0:d} --cpuset-mems={1:d}'.format(self.processor, self.mem)

  def id(self):
    return util.shell_output('docker inspect --format="{{{{.Id}}}}" {0:s}'.format(self.name)).strip()

  def start(self):
    # TODO: X-Container
    v = ''
    if self.config() != '':
      v = '-v {0:s}'.format(self.config())

    p = ''
    if self.ports() != '':
      p = '-p {0:s}'.format(self.ports())

    util.shell_call('docker run --name {0:s} {1:s} {2:s} {3:s} -d {4:s} {5:s}'.format(self.name, self.cpuset(), v, p, self.application, self.args()), True)
    time.sleep(5)

  def setup(self):
    # Do nothing
    return


class XContainer(DockerContainer):
  def __init__(self, name, application, ip_offset, processor='default'):
    Container.__init__(self, name, 'xcontainer', application, processor)
    self.tmux_name = '{0:s}_xcontainer'.format(name)
    self.ip_offset = ip_offset

  def destroy(self):
    util.shell_call('xl destroy {0:s}'.format(self.name))
    DockerContainer.destroy(self)
    util.shell_call('tmux kill-session -t {0:s}'.format(self.tmux_name))

  def cpuset(self):
    return ''

  def bridge_ip(self):
    return util.get_ip_address('xenbr0')

  def ip(self):
    parts = self.bridge_ip().split(".")
    last = int(parts[-1])
    # Choose next IP address as X-Container IP
    new_last = (last + self.ip_offset) % 255
    parts[-1] = str(new_last)
    return ".".join(parts)

  def machine_ip(self):
    return util.get_ip_address('em1')

  def start(self):
    util.shell_call('tmux new -s {0:s} -d'.format(self.tmux_name), True)
    DockerContainer.start(self)

  def setup(self):
    util.shell_call('docker stop {0:s}'.format(self.name))
    time.sleep(1)
    util.tmux_command(self.tmux_name, 'cd /root/experiments/native/compute06/docker')
    util.tmux_command(self.tmux_name, 'python run.py --id {0:s} --ip {1:s} --hvm --name {2:s} --cpu=1'.format(DockerContainer.id(self), self.ip(), self.name))
    time.sleep(10)


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
  def __init__(self):
    DockerContainer.__init__(self, 'memcached_container', 'memcached')

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


class MemcachedXContainer(XContainer, MemcachedDockerContainer):
  def __init__(self):
    XContainer.__init__(self, 'memcached_container', 'memcached', 1)

  def setup(self):
    XContainer.setup(self)
    MemcachedDockerContainer.setup_port_forwarding(self, self.machine_ip(), self.port, self.ip(), self.port, self.bridge_ip())
    MemcachedDockerContainer.benchmark_message(self)


class MemcachedLinuxContainer(LinuxContainer, ApplicationContainer, Memcached):
  def __init__(self):
    LinuxContainer.__init__(self, 'memcached_container', 'memcached')

  def setup(self):
    LinuxContainer.setup(self)
    LinuxContainer.execute_command(self, 'apt-get install -y memcached')
    util.tmux_command(self.tmux_name, 'lxc-attach -n {0:s}'.format(self.name))
    time.sleep(1)
    util.tmux_command(self.tmux_name, Memcached.start_command(self, self.ip()))
    time.sleep(1)
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

  def start(self):
    util.shell_call('tmux new -s {0:s} -d'.format(self.tmux_name))

  def setup(self):
    util.tmux_command(self.tmux_name, 'apt-get update')
    time.sleep(5)
    util.tmux_command(self.tmux_name, 'apt-get install -y git')
    time.sleep(40)
    util.tmux_command(self.tmux_name, 'apt-get install -y make')
    time.sleep(5)
    util.tmux_command(self.tmux_name, 'apt-get install -y ca-certificates')
    time.sleep(8)
    util.tmux_command(self.tmux_name, 'apt-get install -y g++')
    time.sleep(90)
    util.tmux_command(self.tmux_name, 'cd /home; git clone https://sj677:d057c5e8f966db42a6f467c6029da686fdcf4bb4@github.coecis.cornell.edu/SAIL/XcontainerBolt.git')
    time.sleep(8)
    util.tmux_command(self.tmux_name, 'cd /home/XcontainerBolt/uBench; make')
    time.sleep(10)

  def benchmark(self):
    args = ''
    if self.metric.startswith('mem'):
      args = '{0:d} {1:d}'.format(self.duration, self.intensity)
    elif self.metric.startswith('cpu'):
      args = '{0:d}'.format(self.duration)
    else:
      raise Exception('benchmark - not implemented')
    util.tmux_command(self.tmux_name, '/home/XcontainerBolt/uBench/src/{0:s} {1:s}'.format(self.metric, args))

  def destroy(self):
    util.shell_call('tmux kill-session -t {0:s}'.format(self.tmux_name))


class BenchmarkLinuxContainer(LinuxContainer, BenchmarkContainer):
  def __init__(self, metric, intensity, application, processor):
    name = 'benchmark_linux_container'
    LinuxContainer.__init__(self, name, application, processor)
    BenchmarkContainer.__init__(self, metric, intensity, name, 'linux', application, processor)

  def setup(self):
    LinuxContainer.setup(self)
    util.tmux_command(self.tmux_name, 'lxc-attach --name {0:s}'.format(self.name))
    time.sleep(2)
    BenchmarkContainer.setup(self)

  def destroy(self):
    LinuxContainer.destroy(self)
    BenchmarkContainer.destroy(self)


class BenchmarkDockerContainer(DockerContainer, BenchmarkContainer):
  def __init__(self, metric, intensity, application, processor, name='benchmark_docker_container', container='docker'):
    DockerContainer.__init__(self, name, 'bash', processor)
    BenchmarkContainer.__init__(self, metric, intensity, name, container, application, processor)

  def setup(self):
    time.sleep(1)
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
    time.sleep(10)
    util.tmux_command(self.tmux_name, 'docker run --name {0:s} {1:s} -i ubuntu /bin/bash'.format(self.name, self.cpuset()))


class BenchmarkXContainer(XContainer, BenchmarkDockerContainer, BenchmarkContainer):
  def __init__(self, metric, intensity, application, processor):
    name = 'benchmark_xcontainer'
    XContainer.__init__(self, name, 'bash', 2, processor)
    BenchmarkDockerContainer.__init__(self, metric, intensity, application, processor, name, 'xcontainer')

  def setup(self):
    BenchmarkContainer.setup(self)
    util.shell_call('sudo docker stop {0:s}'.format(self.name))  # TODO: Replace
    time.sleep(5)
    XContainer.setup(self)
    time.sleep(10)

  def destroy(self):
    XContainer.destroy(self)
    BenchmarkContainer.destroy(self)

  def cpu(self):
    return ''

  def start(self):
    BenchmarkDockerContainer.start(self)


def get_benchmark_processor(test):
  if ('same-container' in test) or ('same-core' in test):
    return 'default'
  elif ('different-logical-core' in test):
    return 'logical'
  elif ('different-core' in test):
    return 'different'
  elif ('bare' in test):
    return ''
  else:
    raise Exception('container.get_benchmark_processor: Not implemented')


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


def balance_xcontainer(b, m, p):
  util.shell_call('python /root/x-container/irq-balance.py')
  util.shell_call('xl cpupool-migrate {0:s} Pool-node0'.format(m.name))
  util.shell_call('xl vcpu-pin {0:s} 0 {1:d}'.format(m.name, m.processor), True)
  if b is not None:
    if p == 'logical':
      util.shell_call('xl cpupool-migrate {0:s} Pool-node1'.format(b.name), True)
    else:
      util.shell_call('xl cpupool-migrate {0:s} Pool-node0'.format(b.name), True)
    util.shell_call('xl vcpu-pin {0:s} 0 {1:d}'.format(b.name, b.processor), True)


def create_application_container(args):
  if args.container == 'linux':
    m = MemcachedLinuxContainer()
  elif args.container == 'docker':
    m = MemcachedDockerContainer()
  elif args.container == 'xcontainer':
    m = MemcachedXContainer()
  else:
    raise Exception("create_application_container: not implemented")
  return m


def create_benchmark_container(args):
  p = get_benchmark_processor(args.test)
  b = None

  if p != '':
    if args.container == 'linux':
      b = BenchmarkLinuxContainer(args.metric, args.intensity, args.application, p)
    elif args.container == 'docker':
      b = BenchmarkDockerContainer(args.metric, args.intensity, args.application, p)
    elif args.container == 'xcontainer':
      b = BenchmarkXContainer(args.metric, args.intensity, args.application, p)
  return b


def setup_containers(args):
  if args.container == 'xcontainer':
    util.shell_call('xl cpupool-numa-split')
  if 'same-container' in args.test:
    raise Exception('not implemented yet')
  else:
    m = create_application_container(args)
    b = create_benchmark_container(args)

    if args.destroy:
      m.destroy()
      if b is not None:
        b.destroy()
    else:
      m.start()
      m.setup()

      if b is not None:
        b.start()
        b.setup()
        b.benchmark()

      if args.container == 'xcontainer':
        balance_xcontainer(b, m, get_benchmark_processor(args.test))


def main():
  args = parse_arguments()
  setup_containers(args)


if __name__ == '__main__':
  main()
