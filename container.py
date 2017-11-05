import subprocess
import time
import util


class Memcached(object):
  port = 11211
  size = 512
  threads = 4


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
    util.shell_call('sudo tmux kill-session -t {0:s}'.format(self.tmux_name))
    util.shell_call('sudo lxc-stop --name {0:s}'.format(self.name))
    util.shell_call('sudo lxc-destroy --name {0:s}'.format(self.name))

  def execute_command(self, command):
    util.shell_call('sudo lxc-attach --name {0:s} -- /bin/sh -c "{1:s}"'.format(self.name, command), True)

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
    util.shell_call('sudo lxc-create --name {0:s} -t ubuntu'.format(self.name), True)
    util.shell_call('sudo lxc-start --name {0:s} -d'.format(self.name), True)
    util.shell_call("sudo lxc-cgroup -n {0:s} cpuset.cpus {1:d}".format(self.name, self.processor))
    util.shell_call('sudo tmux new -s {0:s} -d'.format(self.tmux_name), True)
    # Need to sleep to let container establish network connection
    time.sleep(5)

  def setup(self):
    self.execute_command('sudo apt-get update')


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
    print("To benchmark run 'python docker_setup.py -c {0:s} -p {0:s}'".format(self.container, self.application))


class MemcachedLinuxContainer(LinuxContainer, ApplicationContainer, Memcached):
  def __init__(self, processor):
    LinuxContainer.__init__(self, 'memcached_container', 'memcached', processor)

  def setup(self):
    LinuxContainer.setup(self)
    LinuxContainer.execute_command(self, 'sudo apt-get install -y memcached')
    #self.execute_command('/etc/init.d/memcached stop')
    # TODO: Do I need a config?
    # self.execute_command('sudo truncate -s0 /etc/memcached.conf')
    util.tmux_command(self.tmux_name, 'sudo lxc-attach -n {0:s}'.format(self.name))
    time.sleep(1)
    util.tmux_command(self.tmux_name, 'memcached -m {0:d} -u root -p {1:d} -l {2:s} -t {3:d}'.format(self.size, self.port, self.ip(), self.threads))
    # util.shell_call("sudo lxc-cgroup -n {0:s} memory.limit_in_bytes 1G".format(self.name))
    util.shell_call("sudo lxc-cgroup -n {0:s} cpuset.cpus {1:d}".format(self.name, self.processor))
    ApplicationContainer.setup_port_forwarding(self, self.machine_ip(), self.port, self.ip(), self.port, self.bridge_ip())
    ApplicationContainer.benchmark_message(self)


class BenchmarkContainer(Container):
  def __init__(self, metric, name, container, application, processor):
    Container.__init__(self, name, container, application, processor)
    self.metric = metric
    self.duration = 7200

  def setup(self):
    self.execute_command('apt-get update')
    self.execute_command('apt-get install -y git')
    self.execute_command('apt-get install -y make')
    self.execute_command('apt-get install -y g++')
    self.execute_command('apt-get install -y ca-certificates')
    self.execute_command('git clone https://github.coecis.cornell.edu/SAIL/XcontainerBolt.git')
    self.execute_command('cd XcontainerBolt/uBench; make')

  def benchmark(self):
    self.execute_command('cd XcontainerBolt/uBench; src/{0:s} {1:d}'.format(self.metric, self.duration))


class BenchmarkLinuxContainer(LinuxContainer, BenchmarkContainer):
  def __init__(self, metric, name, application, processor):
    LinuxContainer.__init__(self, name, application, processor)
    BenchmarkContainer.__init__(self, metric, name, 'linux', application, processor)

  def setup(self):
    LinuxContainer.setup(self)
    BenchmarkContainer.setup(self)


if __name__ == '__main__':
  m = MemcachedLinuxContainer(util.processor(0))
  m.start()
  m.setup()
  #m.destroy()

  b = BenchmarkLinuxContainer('cpu', 'benchmark_linux_container', 'memcached', util.processor(0))
  b.start()
  b.setup()
  b.benchmark()
  #b.destroy()
