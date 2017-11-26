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
    return 'memcached -m {0:d} -u root -p {1:d} {2:s} -t {3:d} &'.format(self.size, self.port, addr, self.threads)

class Nginx(object):
  port = 80

class Container(object):
  def __init__(self, name, container, application, processor_type):
    self.application = application
    self.container = container
    self.name = name
    print("processor_type", processor_type)
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
    ip = util.get_ip_address('eno1')
    if ip is None or ip == '':
      ip = util.get_ip_address('enp67s0')
    return ip

  def setup(self):
    raise Exception('Container-setup: Not implemented')

  def start(self):
    raise Exception('Container-start: Not implemented')


class LinuxContainer(Container):
  def __init__(self, name, application, processor='default'):
    Container.__init__(self, name, 'linux', application, processor)
    self.tmux_name = 'linux'

  def copy_folder(self, folder):
    util.shell_call('find {0:s} | cpio -o | lxc-attach --name {1:s} -- cpio -i -d -v'.format(folder, self.name), True)
    self.execute_command('mv {0:s} home/{0:s}'.format(folder))

  def setup_benchmark(self):
    util.tmux_command(self.tmux_name, 'lxc-attach --name {0:s}'.format(self.name))
    BenchmarkContainer.setup(self, False)

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
    util.shell_call('docker exec  --user root -it {0:s} {1:s}'.format(self.name, command), True)

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

  def xconfig(self):
    nodeId = 0
    if self.processor > 12:
      nodeId = 1
    return """
builder='hvm'
serial='pty'

#kernel = "/root/ubuntu16/kernel/vmlinuz-4.4.44"
#ramdisk = "/root/ubuntu/initrd.img-3.19.8-xenct"
#ramdisk = "/root/ubuntu16/initrd/initrd.img-4.4.44.new"
#extra = "docker root=/dev/xvda rw noplymouth noresume $vt_handoff earlyprintk=xen vsyscall=native console=hvc0 ip=::::VM_NAME:eth0:dhcp quiet"

name = "VM_NAME"
memory = "8192"
#memory = 16000
#disk = [ '/root/ubuntu/disk.qcow2,qcow2,xvda,rw', '/dev/mapper/test,raw,xvdb,rw']
disk = [ '/root/experiments/native/compute06/docker/IMAGE_NAME,qcow2,xvda,rw', 'DEVICE_NAME,raw,xvdb,rw', "/root/experiments/native/compute06/docker/ISO_NAME,raw,xvdc:cdrom,r"]
#disk = [ '/root/ubuntu/disk.img,raw,xvda,rw']
vif = [ 'mac=MAC_ADDR,bridge=xenbr0,type=vif' ]
vcpus = VM_CPU
#cpus_soft = ["0", "1", "2", "3"]
#vfb = [ 'type=vnc' ]
vnc = 0
nographic = 1
on_reboot = 'restart'
on_crash = 'preserve'
#bootloader= 'pygrub'
device_model_version = "qemu-xen"
pool="Pool-node{0:d}"
    """.format(nodeId)

  def create_xconfig(self):
    filename = '/root/experiments/native/compute06/docker/docker_hvm.cfg'
    util.shell_call('truncate -s0 {0:s}'.format(filename))
    f = open(filename, 'w+')
    f.write(self.xconfig())
    f.close

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
    self.create_xconfig()
    util.tmux_command(self.tmux_name, 'cd /root/experiments/native/compute06/docker')
    util.tmux_command(self.tmux_name, 'python run.py --id {0:s} --ip {1:s} --hvm --name {2:s} --cpu=1'.format(DockerContainer.id(self), self.ip(), self.name))
    time.sleep(10)


class BenchmarkContainer(Container):
  def __init__(self, metric, intensity, name, container, application, processor):
    Container.__init__(self, name, container, application, processor)
    self.metric = metric
    self.intensity = intensity
    self.duration = 7200
    self.tmux_name = 'benchmark'
    self.num_interferences = 3

  def start(self):
    util.shell_call('tmux new -s {0:s} -d'.format(self.tmux_name))

  def destroy(self):
    util.shell_call('tmux kill-session -s {0:s}'.format(self.tmux_name))

  def benchmark_makefile(self):
    return '''#.ONESHELL:
default:
\\tcd src;\\\\\\\\
\\tg++ -o memCap memCap.c -lrt;\\\\\\\\
\\tg++ -o memBw memBw.c;\\\\
\\tg++ -fopenmp -o cpu cpu.cpp -lpthread -lgomp;\\\\
\\tg++ -o cpu2 cpu2.cpp;\\\\
\\tg++ -o l1i l1i.c -lrt;\\\\
\\tg++ -o l1d l1d.c -lrt;\\\\
\\tg++ -o l3 l3.c -lrt;\\\\
\\tg++ -o l2 l2.c -lrt;\\\\

memCap:
\\tcd src;\\\\
\\tg++ -o memCap memCap.c -lrt;\\\\

memBw:
\\tcd src;\\\\
\\tg++ -o memBw memBw.c;\\\\

cpu:
\\tcd src;\\\\
\\tg++ -fopenmp -o cpu cpu.cpp -lpthread -lgomp;\\\\

cpu2:
\\tcd src;\\\\
\\tg++ -o cpu2 cpu2.cpp;\\\\

l1i:
\\tcd src;\\\\
\\tg++ -o l1i l1i.c -lrt;\\\\

l1d:
\\tcd src;\\\\
\\tg++ -o l1d l1d.c -lrt;\\\\

l2:
\\tcd src;\\\\
\\tg++ -o l2 l2.c -lrt;\\\\
'''

  def setup(self, useYum=False):
    command = 'apt-get'
    install = 'apt-get install -y'
    if useYum:
      command = 'yum'
      install = 'yum -y install'
    util.tmux_command(self.tmux_name, '{0:s} update'.format(command))
    time.sleep(5)
#    util.tmux_command(self.tmux_name, '{0:s} git'.format(install))
#    time.sleep(40)
    util.tmux_command(self.tmux_name, '{0:s} make'.format(install))
    time.sleep(5)
#    util.tmux_command(self.tmux_name, '{0:s} ca-certificates'.format(install))
#    time.sleep(8)
    util.tmux_command(self.tmux_name, '{0:s} g++'.format(install))
    time.sleep(100)
#    util.tmux_command(self.tmux_name, 'cd /home; git clone https://sj677:d057c5e8f966db42a6f467c6029da686fdcf4bb4@github.coecis.cornell.edu/SAIL/XcontainerBolt.git')
#    time.sleep(8)
#    util.tmux_command(self.tmux_name, 'cd /home/XcontainerBolt/uBench; truncate -s0 Makefile')
#    for line in self.benchmark_makefile().split('\n'):
#      util.tmux_command(self.tmux_name, "echo -e '{0:s}' >> Makefile".format(line))
    if False:
      util.tmux_command(self.tmux_name, 'yum -y install libmpc-devel mpfr-devel gmp-devel')
      time.sleep(10)
      util.tmux_command(self.tmux_name, 'curl ftp://ftp.mirrorservice.org/sites/sourceware.org/pub/gcc/releases/gcc-4.9.2/gcc-4.9.2.tar.bz2 -O')
      time.sleep(60)
      util.tmux_command(self.tmux_name, 'tar xvfj gcc-4.9.2.tar.bz2')
      time.sleep(2)
      util.tmux_command(self.tmux_name, 'cd gcc-4.9.2')
      util.tmux_command(self.tmux_name, './configure --disable-multilib --enable-languages=c,c++')
      time.sleep(5)
      util.tmux_command(self.tmux_name, 'make -j4')
      time.sleep(5)
      util.tmux_command(self.tmux_name, 'make install')
      time.sleep(600)
#    print("making uBench")
    util.tmux_command(self.tmux_name, 'cd /home/XcontainerBolt/uBench; make')
    print("sleeping...")
    time.sleep(100)
    print("setting up benchmark")
    self.benchmark()

  def benchmark(self):
    args = ''
    if self.metric.startswith('mem') or self.metric.startswith('l3'):
      args = '{0:d} {1:d}'.format(self.duration, self.intensity)
    elif self.metric.startswith('cpu'):
      args = '{0:d}'.format(self.duration)
    else:
      raise Exception('benchmark - not implemented')
    for i in range(self.num_interferences):
      print("Starting 1 interfere", i)
      util.tmux_command(self.tmux_name, '/home/XcontainerBolt/uBench/src/{0:s} {1:s} &'.format(self.metric, args))

  def destroy(self):
    util.shell_call('tmux kill-session -t {0:s}'.format(self.tmux_name))


class ApplicationContainer(Container):
  def setup_port_forwarding(self, machine_ip, machine_port, container_ip, container_port, bridge_ip):
    util.shell_call('iptables -I FORWARD -p tcp -d {0:s} -j ACCEPT'.format(container_ip), True)
    time.sleep(1)
    util.shell_call('iptables -I FORWARD -p tcp -s {0:s} -j ACCEPT'.format(container_ip), True)
    time.sleep(1)
    util.shell_call('iptables -I INPUT -m state --state NEW -p tcp -m multiport --dport {0:d} -s 0.0.0.0/0 -j ACCEPT'.format(machine_port), True)
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
    include /etc/nginx/sites-enabled/*;
}
'''


def setup_nginx_configuration(configuration_file_path):
  f = open(configuration_file_path, 'w')
  f.write(get_nginx_configuration())
  f.close


class NginxDockerContainer(DockerContainer, ApplicationContainer, Nginx, BenchmarkContainer):
  def __init__(self, sameContainer=False, metric=None, intensity=None):
    self.config_file = '/dev/nginx.conf'
    self.docker_tmux_name = 'nginx_docker'
    util.shell_call('tmux new -s {0:s} -d'.format(self.docker_tmux_name))
    util.shell_call('tmux new -s {0:s} -d'.format("benchmark"))
    DockerContainer.__init__(self, 'nginx_container', 'nginx')
    self.sameContainer = sameContainer

    if sameContainer:
      BenchmarkContainer.__init__(self, metric, intensity, self.name, 'docker', 'nginx', 'default')

  def config(self):
    return ''

  def ports(self):
    return '0.0.0.0:{0:d}:{0:d}'.format(self.port)

  def args(self):
    return ''

  def start(self):
    #setup_nginx_configuration(self.config_file)
    DockerContainer.start(self)

  def setup_config(self):
    util.tmux_command(self.docker_tmux_name, 'docker exec -it {0:s} /bin/bash'.format(self.name))
    util.tmux_command(self.docker_tmux_name, 'truncate -s0 etc/nginx/nginx.conf')
    for line in get_nginx_configuration().split('\n'):
      util.tmux_command(self.docker_tmux_name, "echo '{0:s}' >> etc/nginx/nginx.conf".format(line))
    util.tmux_command(self.docker_tmux_name, 'exit')

  def setup_benchmark(self):
    util.tmux_command(self.tmux_name, 'docker exec -it {0:s} /bin/bash'.format(self.name))
    BenchmarkContainer.setup(self, False)

  def setup(self):
    DockerContainer.setup(self)
    self.setup_config()
    if self.sameContainer:
      util.shell_call('docker cp XcontainerBolt {0:s}:/home/XcontainerBolt'.format(self.name), True)
      self.setup_benchmark()
    ApplicationContainer.setup_port_forwarding(self, self.machine_ip(), self.port, self.ip(), self.port, self.bridge_ip())
    ApplicationContainer.benchmark_message(self)

  def destroy(self):
    DockerContainer.destroy(self)
    util.shell_call('tmux kill-session -t {0:s}'.format(self.docker_tmux_name))
    util.shell_call('tmux kill-session -t {0:s}'.format("benchmark"))


class MemcachedDockerContainer(DockerContainer, ApplicationContainer, Memcached, BenchmarkContainer):
  def __init__(self, sameContainer=False, metric=None, intensity=None):
    DockerContainer.__init__(self, 'memcached_container', 'memcached')
    util.shell_call('tmux new -s {0:s} -d'.format("benchmark"))
    self.sameContainer = sameContainer

    if sameContainer:
      BenchmarkContainer.__init__(self, metric, intensity, self.name, 'docker', 'memcached', 'default')

  def destroy(self):
    DockerContainer.destroy(self)
    if self.sameContainer:
      BenchmarkContainer.destroy(self)
  def setup_benchmark(self):
    util.tmux_command(self.tmux_name, 'docker exec --user root -it {0:s} /bin/bash'.format(self.name))
    BenchmarkContainer.setup(self, False)
  def config(self):
    return ""

  def ports(self):
    return '0.0.0.0:{0:d}:{0:d}'.format(self.port)

  def args(self):
    return Memcached.start_command(self)

  def setup(self):
    DockerContainer.setup(self)
    if self.sameContainer:
      util.shell_call('docker cp XcontainerBolt {0:s}:/home/XcontainerBolt'.format(self.name), True)
      self.setup_benchmark()
    ApplicationContainer.setup_port_forwarding(self, self.machine_ip(), self.port, self.ip(), self.port, self.bridge_ip())
    ApplicationContainer.benchmark_message(self)


class MemcachedXContainer(XContainer, MemcachedDockerContainer):
  def __init__(self):
    XContainer.__init__(self, 'memcached_container', 'memcached', 1)

  def setup(self):
    XContainer.setup(self)
    MemcachedDockerContainer.setup_port_forwarding(self, self.machine_ip(), self.port, self.ip(), self.port, self.bridge_ip())
    MemcachedDockerContainer.benchmark_message(self)


class NginxXContainer(XContainer, NginxDockerContainer):
  def __init__(self, sameContainer=False, metric=None, intensity=None):
    print("init 1")
    NginxDockerContainer.__init__(self, sameContainer, metric, intensity)
    XContainer.__init__(self, 'nginx_container', 'nginx', 1)
    print("init 2")

  def setup(self):
    print("setup 1")
    NginxDockerContainer.setup_config(self)
    print("setup 2")
    if self.sameContainer:
      NginxDockerContainer.setup_benchmark(self)
    print("setup 3")
    #util.shell_call("service docker restart")
    #XContainer.setup(self)
    NginxDockerContainer.setup_port_forwarding(self, self.machine_ip(), self.port, self.ip(), self.port, self.bridge_ip())
    print("setup 4")
    NginxDockerContainer.benchmark_message(self)
    #NginxDockerContainer.benchmark(self)
    print("setup 5")

  def destroy(self):
    XContainer.destroy(self)
    NginxDockerContainer.destroy(self)


class MemcachedLinuxContainer(LinuxContainer, ApplicationContainer, Memcached, BenchmarkContainer):
  def __init__(self, sameContainer=False, metric=None, intensity=None):
    self.sameContainer = sameContainer
    LinuxContainer.__init__(self, 'memcached_container', 'memcached')
    if sameContainer:
      BenchmarkContainer.__init__(self, metric, intensity, self.name, 'linux', 'memcached', 'default')

  def setup(self):
    LinuxContainer.setup(self)
    LinuxContainer.execute_command(self, 'apt-get install -y memcached')
    util.tmux_command(self.tmux_name, 'lxc-attach -n {0:s}'.format(self.name))
    time.sleep(1)
    util.tmux_command(self.tmux_name, Memcached.start_command(self, self.ip()))
    time.sleep(1)
    util.shell_call("lxc-cgroup -n {0:s} cpuset.cpus {1:d}".format(self.name, self.processor))
    if self.sameContainer:
      LinuxContainer.copy_folder(self, 'XcontainerBolt')
      self.setup_benchmark()
    ApplicationContainer.setup_port_forwarding(self, self.machine_ip(), self.port, self.ip(), self.port, self.bridge_ip())
    ApplicationContainer.benchmark_message(self)


class NginxLinuxContainer(LinuxContainer, ApplicationContainer, Nginx, BenchmarkContainer):
  def __init__(self, sameContainer=False, metric=None, intensity=None):
    self.sameContainer = sameContainer
    LinuxContainer.__init__(self, 'nginx_container', 'nginx')

    if sameContainer:
      BenchmarkContainer.__init__(self, metric, intensity, self.name, 'linux', 'nginx', 'default')

  def setup(self):
    LinuxContainer.setup(self)
    LinuxContainer.execute_command(self, 'apt-get install -y nginx')
    time.sleep(15)
    LinuxContainer.execute_command(self, 'truncate -s0 /etc/nginx/nginx.conf')
    for line in get_nginx_configuration().split("\n"):
      LinuxContainer.execute_command(self, "echo '{0:s}' >> /etc/nginx/nginx.conf".format(line))
    LinuxContainer.execute_command(self, '/etc/init.d/nginx restart')
    util.shell_call("lxc-cgroup -n {0:s} cpuset.cpus {1:d}".format(self.name, self.processor))
    if self.sameContainer:
      LinuxContainer.copy_folder(self, 'XcontainerBolt')
      self.setup_benchmark()
    ApplicationContainer.setup_port_forwarding(self, self.machine_ip(), self.port, self.ip(), self.port, self.bridge_ip())
    ApplicationContainer.benchmark_message(self)


class BenchmarkLinuxContainer(LinuxContainer, BenchmarkContainer):
  def __init__(self, metric, intensity, application, processor):
    name = 'benchmark_linux_container'
    LinuxContainer.__init__(self, name, application, processor)
    BenchmarkContainer.__init__(self, metric, intensity, name, 'linux', application, processor)

  def setup(self):
    LinuxContainer.setup(self)
    LinuxContainer.copy_folder(self, 'XcontainerBolt')
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
    util.shell_call('docker cp XcontainerBolt {0:s}:/home/XcontainerBolt'.format(self.name), True)
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
  if metric.startswith('mem') or metric.startswith('l3'):
    intensity = int(parts[1])
  else:
    intensity = 0
  args.metric = metric
  args.intensity = intensity
  return args


def balance_xcontainer(b, m, p):
  util.shell_call('python /root/x-container/irq-balance.py')
  #util.shell_call('xl cpupool-migrate {0:s} Pool-node0'.format(m.name))
  util.shell_call('xl vcpu-pin {0:s} 0 {1:d}'.format(m.name, m.processor), True)
  if b is not None:
    #if p == 'logical':
    #  util.shell_call('xl cpupool-migrate {0:s} Pool-node1'.format(b.name), True)
    #else:
      #util.shell_call('xl cpupool-migrate {0:s} Pool-node0'.format(b.name), True)
    util.shell_call('xl vcpu-pin {0:s} 0 {1:d}'.format(b.name, b.processor), True)


def create_application_container(args, sameContainer=False):
  if args.container == 'linux':
    if args.application == 'memcached':
      if sameContainer:
        m = MemcachedLinuxContainer(sameContainer, args.metric, args.intensity)
      else:
        m = MemcachedLinuxContainer()
    else:
      if sameContainer:
        m = NginxLinuxContainer(sameContainer, args.metric, args.intensity)
      else:
        m = NginxLinuxContainer(sameContainer)
  elif args.container == 'docker':
    if args.application == 'memcached':
      if sameContainer:
        m = MemcachedDockerContainer(sameContainer, args.metric, args.intensity)
      else:
        m = MemcachedDockerContainer(sameContainer)
    else:
      if sameContainer:
        m = NginxDockerContainer(sameContainer, args.metric, args.intensity)
      else:
        m = NginxDockerContainer(sameContainer)
  elif args.container == 'xcontainer':
    if args.application == 'memcached':
      m = MemcachedXContainer(sameContainer)
    else:
      if sameContainer:
        m = NginxXContainer(sameContainer, args.metric, args.intensity)
      else:
        m = NginxXContainer(sameContainer)
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
  #if args.container == 'xcontainer':
  #  util.shell_call('xl cpupool-numa-split')
  if 'same-container' in args.test:
    m = create_application_container(args, True)
    b = None
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
  #    b.benchmark()

    if args.container == 'xcontainer':
      balance_xcontainer(b, m, get_benchmark_processor(args.test))


def main():
  args = parse_arguments()
  setup_containers(args)


if __name__ == '__main__':
  main()
