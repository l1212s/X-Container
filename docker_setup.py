import argparse
import os
import re
import subprocess
import time

NGINX_CONTAINER_NAME = "nginx_container"
NGINX_MACHINE_PORT = 11100
NGINX_CONTAINER_PORT = 80
MEMCACHED_CONTAINER_NAME = "memcached_container"
MEMCACHED_MACHINE_PORT = 11101
MEMCACHED_CONTAINER_PORT = 11211
DOCKER_INSPECT_FILTER = "{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}"
XCONTAINER_INSPECT_FILTER = "{{.NetworkSettings.IPAddress}}"

#################################################################################################
# Common functionality
#################################################################################################

def shell_call(command, showCommand=False):
  if showCommand:
    print('RUNNING COMMAND: ' + command)
  subprocess.Popen(command, shell=True)
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
    shell_call('apt-get install -y {:s}'.format(package))

def install_common_dependencies(packages):
  shell_call('apt-get update')
  install('linux-tools-4.4.0-92-generic', packages)
  install('make', packages)
  install('gcc', packages)

def get_ip_address(name):
  return shell_output("/sbin/ifconfig {0:s} | grep 'inet addr:' | cut -d: -f2 | awk '{{ print $1 }}'".format(name)).strip()

def setup_nginx_configuration(configuration_file_path):
  configuration = '''
user  nginx;
worker_processes  1;

error_log  /var/log/nginx/error.log warn;
pid        /var/run/nginx.pid;

events {
    worker_connections  1024;
}

http {
    include       /etc/nginx/mime.types;
    default_type  application/octet-stream;

    sendfile        off; # disable to avoid caching and volume mount issues

    keepalive_timeout  65;

    include /etc/nginx/conf.d/*.conf;
}
'''
  f = open(configuration_file_path, 'w')
  f.write(configuration)
  f.close

def install_benchmark_dependencies(args):
  shell_call("mkdir benchmark")

  if not os.path.exists('XcontainerBolt'):
    shell_call('git clone https://github.coecis.cornell.edu/SAIL/XcontainerBolt.git')

  path = os.getcwd()

  if args.process == 'nginx':
    packages = get_known_packages()
    install('libssl-dev', packages)
    os.chdir('XcontainerBolt/wrk2')
    shell_call('make')
  elif args.process == 'memcached':
    os.chdir('XcontainerBolt/mutated')
    shell_call('git submodule update --init')
    install('dh-autoreconf', packages)
    shell_call('./autogen.sh')
    shell_call('./configure')
    shell_call('make')

  os.chdir(path)

def run_nginx_benchmark(args, num_connections, num_threads, duration):
  nginx_folder = "benchmark/nginx-{0:s}".format(args.container)
  shell_call("mkdir {0:s}".format(nginx_folder))
  date = shell_output('date +%F-%H-%M-%S').strip()
  instance_folder = "{0:s}/{1:s}".format(nginx_folder, date)
  shell_call("mkdir {0:1}".format(instance_folder))
  print("Putting NGINX benchmarks in {0:s}".format(instance_folder))

  rates = [1, 10, 100, 500, 1000, 1500, 2000, 2500, 3000]
  for rate in rates:
    benchmark_file = "r{0:d}-t{1:d}-c{2:d}-d{3:d}".format(rate, num_threads, num_connections, duration)
    shell_call('XContainerBolt/wrk2/wrk -r{0:d} -t{1:d} -c{2:d} -d{3:d}s http://{4:s}:{5:d}/index.html > {6:s}/{7:s}'
	.format(rate, num_threads, num_connections, duration, args.benchmark_address, NGINX_MACHINE_PORT, instance_folder, benchmark_file), True)

def run_memcached_benchmark(args):
  mutated_folder = 'XContainerBolt/mutated/client/'
  shell_call('{:s}/load_memcache {:s}:{:d}'.format(mutated_folder, args.benchmark_address, MEMCACHED_MACHINE_PORT))
  shell_call('{:s}/mutated_memcache {:s}:{:d}'.format(mutated_folder, args.benchmark_address, MEMCACHED_MACHINE_PORT))

def run_benchmarks(args):
  install_benchmark_dependencies(args)
  if args.process == "nginx":
    run_nginx_benchmark(args, 400, 12, 10)
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
    port = setup_docker(args)
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
  shell_call('iptables -t nat -I PREROUTING --dst {0:s} -p tcp --dport {1:d} -j DNAT --to-destination {2:s}:{3:d}'.format(machine_ip, machine_port, container_ip, container_port))
  linux_sleep(1)
  shell_call('iptables -t nat -I POSTROUTING -p tcp --dst {0:s} --dport {1:d} -j SNAT --to-source {2:s}'.format(container_ip, container_port, bridge_ip))
  linux_sleep(1)
  shell_call('iptables -t nat -I OUTPUT --dst {0:s} -p tcp --dport {1:d} -j DNAT --to-destination {2:s}:{3:d}'.format(machine_ip, machine_port, container_ip, container_port))
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

def setup_xcontainer_nginx_container():
  setup_docker_nginx_container(XCONTAINER_INSPECT_FILTER)
  docker_id = shell_output('docker inspect --format="{{{{.Id}}}}" {0:s}'.format(NGINX_CONTAINER_NAME)).strip()
  bridge_ip = get_ip_address('xenbr0')
  xcontainer_ip = generate_xcontainer_ip(bridge_ip)

  shell_call('docker stop {0:s}'.format(NGINX_CONTAINER_NAME))
  path = os.getcwd()
  os.chdir('/root/experiments/native/compute06/docker')
  machine_ip = get_ip_address('em1')
  setup_port_forwarding(machine_ip, NGINX_MACHINE_PORT, xcontainer_ip, NGINX_CONTAINER_PORT, bridge_ip)
  print 'Setup NGINX X-Container on {0:s}:{1:d}'.format(machine_ip, NGINX_MACHINE_PORT)
  print 'X-Container will take over this terminal....'
  shell_call('python run.py --id {0:s} --ip {1:s} --hvm --name {2:s}'.format(docker_id, xcontainer_ip, NGINX_CONTAINER_NAME))

def setup_xcontainer(args):
  if args.process == "nginx":
    setup_xcontainer_nginx_container()

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
        os.chdir('XcontainerBolt/mutated')
        shell_call('git submodule update --init')
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

def setup_docker_nginx_container(docker_filter):
  configuration_file_path = '/dev/nginx.conf'
  setup_nginx_configuration(configuration_file_path)

  address = docker_ip(NGINX_CONTAINER_NAME, docker_filter)
  if address == None:
    shell_call('docker run --name {0:s} -P -v {1:s}:/etc/nginx/nginx.conf:ro -d nginx'.format(NGINX_CONTAINER_NAME, configuration_file_path))
    linux_sleep(5)
    address = docker_ip(NGINX_CONTAINER_NAME, docker_filter)
 
  ports = nginx_docker_port()
  print("NGINX running on global port {0:s}, container address {1:s} port {2:s}".format(ports[0], address, ports[1]))
  return ports

def setup_docker_memcached_container():
  address = docker_ip(MEMCACHED_CONTAINER_NAME)
  if address == None:
    # TODO: Way to pass in memcached parameters like memory size
    shell_call('docker run --name {:s} -p 0.0.0.0:{:d}:{:d} -d memcached -m 256'
      .format(MEMCACHED_CONTAINER_NAME, MEMCACHED_MACHINE_PORT, MEMCACHED_CONTAINER_PORT)
    )
    address = docker_ip(MEMCACHED_CONTAINER_NAME)

  ports = memcached_docker_port()

  print("memcached running on global port {:s}, container address {:s} port {:s}".format(ports[0], address, ports[1]))
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
    port = setup_docker_nginx_container(DOCKER_INSPECT_FILTER)
  elif args.process == "memcached":
    port = setup_docker_memcached_container()
  return port

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
  shell_call('lxc-attach --name ' + name + ' -- /bin/sh -c "' + command + '"')

def get_linux_container_ip(name):
  try:
    output = shell_output('lxc-info -n {:s} -iH'.format(name))
    return output.decode('utf-8').strip()
  except subprocess.CalledProcessError as e:
    return None

def setup_linux(args):
  install_linux_dependencies()
  if args.process == "nginx":
    container_ip = get_linux_container_ip(NGINX_CONTAINER_NAME)
    container_port = NGINX_CONTAINER_PORT
    machine_port = NGINX_MACHINE_PORT

    if container_ip != None:
      return

    setup_linux_nginx_container()
    container_ip = get_linux_container_ip(NGINX_CONTAINER_NAME)
  elif args.process == "memcached":
    container_ip = get_linux_container_ip(MEMCACHED_CONTAINER_NAME)
    container_port = MEMCACHED_CONTAINER_PORT
    machine_port = MEMCACHED_MACHINE_PORT

    if container_ip != None:
      return

    setup_linux_memcached_container()
    container_ip = get_linux_container_ip(MEMCACHED_CONTAINER_NAME)
  else:
    raise "setup_linux: Not implemented"
  print("machine port", machine_port, "container ip", container_ip, "container port", container_port)
  setup_port_forwarding(machine_port, container_ip, container_port)

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
  linux_container_execute_command(NGINX_CONTAINER_NAME, 'systemctl status nginx')

def setup_linux_memcached_container():
  start_linux_container(MEMCACHED_CONTAINER_NAME)
  linux_sleep(5)
  linux_container_execute_command(MEMCACHED_CONTAINER_NAME, 'sudo apt-get update')
  linux_container_execute_command(MEMCACHED_CONTAINER_NAME, 'sudo apt-get install -y memcached')
  linux_container_execute_command(MEMCACHED_CONTAINER_NAME, 'memcached -u root &')

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
  # python docker_setup.py -p nginx -b 1.2.3.4
  parser = argparse.ArgumentParser()
  parser.add_argument('-c', '--container', help='Indicate type of container (docker, linux)')
  parser.add_argument('-p', '--process', required=True, help='Indicate which process to run on docker (NGINX, Spark, etc)')
  parser.add_argument('-b', '--benchmark_address', type=str, help='Address to benchmark (localhost or 1.2.3.4)')
  parser.add_argument('-d', '--destroy', action='store_true', default=False, help='Destroy associated container')
  args = parser.parse_args()

  if args.benchmark_address != None:
    run_benchmarks(args) 
  elif args.destroy:
    destroy_container(args)
  else:
    setup(args) 
