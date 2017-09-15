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

#################################################################################################
# Common functionality
#################################################################################################

def call(command):
  print('RUNNING COMMAND: ' + ' '.join(command))
  subprocess.call(command)
  print('')

def shell_call(command):
  print('RUNNING COMMAND: ' + command)
  subprocess.call(command, shell=True)
  print('')

def get_known_packages():
  output = subprocess.check_output(['dpkg', '--get-selections']).decode('utf-8')
  lines = output.split('\n')
  packages = list(map(lambda x: x.split('\t')[0], lines))
  packages = list(filter(lambda x: len(x) > 0, packages))
  return packages

def install(package, known_packages):
  if package in known_packages:
    print(package + " has already been installed")
  else:
    call(['apt-get', 'install', '-y', package])

def install_common_dependencies(packages):
  shell_call('apt-get update')
  install('linux-tools-4.4.0-92-generic', packages)
  install('make', packages)
  install('gcc', packages)

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
  shell_call('XContainerBolt/wrk2/wrk -t{:d} -c{:d} -d{:d}s http://{:s}:{:d}/index.html'
	.format(num_threads, num_connections, duration, args.benchmark_address, NGINX_MACHINE_PORT))

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
  else:
    raise "destroy_container: Not implemented"

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

def setup_docker_nginx_container():
  configuration_file_path = '/dev/nginx.conf'
  setup_nginx_configuration(configuration_file_path)

  address = docker_ip(NGINX_CONTAINER_NAME)
  if address == None:
    shell_call('docker run --name {:s} -P -v {:s}:/etc/nginx/nginx.conf:ro -d nginx'.format(NGINX_CONTAINER_NAME, configuration_file_path))
    address = docker_ip(NGINX_CONTAINER_NAME)
 
  ports = nginx_docker_port()
  print("NGINX running on global port {:s}, container address {:s} port {:s}".format(ports[0], address, ports[1]))
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
    output = subprocess.check_output('docker port {:s}'.format(name), shell=True).decode('utf-8')
    results = re.findall(regex, output)
    if len(results) == 0:
      return None
    else:
      return list(results[0])
  except subprocess.CalledProcessError as e:
    return None

def docker_ip(name):
  try:
    output = subprocess.check_output("docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' " + name, shell=True)
    return output.decode('utf-8').strip()
  except subprocess.CalledProcessError as e:
    return None

def setup_docker(args):
  install_docker_dependencies()
  if args.process == "nginx":
    port = setup_docker_nginx_container()
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

def setup_port_forwarding(machine_port, container_ip, container_port):
  print("machine port", machine_port, "container ip", container_ip, "container port", container_port)
  shell_call('iptables -t nat -A PREROUTING -p tcp -i eth0 --dport {:d} -j DNAT --to-destination {:s}:{:d}'.format(machine_port, container_ip, container_port))
  shell_call('iptables -t nat -A POSTROUTING -p tcp -d {:s} --dport {:d} -j MASQUERADE'.format(container_ip, container_port))

def get_linux_container_ip(name):
  try:
    output = subprocess.check_output('lxc-info -n {:s} -iH'.format(name), shell=True)
    return output.decode('utf-8').strip()
  except subprocess.CalledProcessError as e:
    return None

def setup_linux(args):
  install_linux_dependencies()
  if args.process == "nginx":
    container_ip = get_linux_container_ip(NGINX_CONTAINER_NAME)
    machine_port = NGINX_MACHINE_PORT

    if container_ip != None:
      return

    container_port = setup_linux_nginx_container()
    container_ip = get_linux_container_ip(NGINX_CONTAINER_NAME)
  elif args.process == "memcached":
    container_ip = get_linux_container_ip(MEMCACHED_CONTAINER_NAME)
    container_port = MEMCACHED_MACHINE_PORT

    if container_ip != None:
      return

    container_port = setup_linux_memcached_container()
    container_ip = get_linux_container_ip(MEMCACHED_CONTAINER_NAME)
  else:
    raise "setup_linux: Not implemented"
  print("machine port", machine_port, "container ip", container_ip, "container port", container_port)
  setup_port_forwarding(machine_port, container_ip, container_port)

def start_linux_container(name):
  # TODO: Is this the template we want?
  shell_call('lxc-create --name ' + name + ' -t ubuntu')
  shell_call('lxc-start --name ' + name + ' -d')

def linux_sleep():
  num_seconds = 5
  print("Sleeping for {:d} seconds. Linux container network setup is slow....".format(num_seconds))
  time.sleep(num_seconds)

def setup_linux_nginx_container():
  start_linux_container(NGINX_CONTAINER_NAME)
  linux_sleep()
  linux_container_execute_command(NGINX_CONTAINER_NAME, 'sudo apt-get update')
  linux_container_execute_command(NGINX_CONTAINER_NAME, 'sudo apt-get install -y nginx') 
  linux_container_execute_command(NGINX_CONTAINER_NAME, 'systemctl status nginx')

def setup_linux_memcached_container():
  start_linux_container(MEMCACHED_CONTAINER_NAME)
  linux_sleep()
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
  elif args.container == "docker":
    port = setup_docker(args)
  elif args.container == "linux":
    setup_linux(args) 
