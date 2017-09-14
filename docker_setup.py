import argparse
import os
import re
import subprocess

NGINX_CONTAINER_NAME = "nginx_container"
MEMCACHED_CONTAINER_NAME = "memcached_container"

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

def install_dependencies():
  packages = get_known_packages()

  call(['apt-get', 'update'])
  install('linux-tools-4.4.0-92-generic', packages)
  install('make', packages)
  install('gcc', packages)

  # apt-get may not know about about docker
  if 'docker-ce' in packages:
    print('docker-ce has already been installed')
  else:
    shell_call('curl -fsSL https://download.docker.com/linux/ubuntu/gpg | apt-key add -')
    shell_call('add-apt-repository "deb [arch=amd64] https://download.docker.com/linux/ubuntu xenial stable"')

    call(['apt-get', 'update'])
    call(['apt-get', 'install', '-y', 'docker-ce'])

  # idk if there's a bette way to do this
  if not os.path.exists("wrk"):
    call(['git', 'clone', 'https://github.com/wg/wrk.git'])
    call(['make', '-j4', '-C', 'wrk'])

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

def docker_port(regex):
  output = subprocess.check_output(['docker', 'ps']).decode('utf-8')
  results = re.findall(regex, output)
  if len(results) == 0:
    return None
  else:
    return results[0]

def nginx_docker_port():
  return docker_port('0.0.0.0:([0-9]+)->80/tcp')

def memcached_docker_port():
  return docker_port('([0-9]+)/tcp')

def setup_nginx_container():
  configuration_file_path = '/dev/nginx.conf'
  setup_nginx_configuration(configuration_file_path)

  port = nginx_docker_port()
  if port == None:
    call([
      'docker', 'run', '--name', NGINX_CONTAINER_NAME,
      '-P', '-v', configuration_file_path + ':/etc/nginx/nginx.conf:ro',
      '-d', 'nginx'
    ])
    port = nginx_docker_port()
 
  print("NGINX running on port " + port)
  return port

def setup_memcached_container():
  port = memcached_docker_port()
  if port == None:
    # TODO: Way to pass in memcached parameters like memory size
    shell_call('docker run --name memcached ' + MEMCACHED_CONTAINER_NAME + ' -d memcached -m 256'
    port = memcached_docker_port()

  print("memcached running on port " + port)
  return port

def run_nginx_benchmark(num_connections, num_threads, duration, port, measure_performance):
  command = [
    "wrk/wrk",
    "-t{:d}".format(num_threads),
    "-c{:d}".format(num_connections),
    "-d{:d}s".format(duration),
    "http://localhost:{:s}/index.html".format(port)
  ]
  if measure_performance:
    command = ['perf', 'stat'] + command
  call(command)

def destroy_nginx_container():
  call(['docker', 'stop', NGINX_CONTAINER_NAME])
  call(['docker', 'rm', NGINX_CONTAINER_NAME])

def setup_docker(args):
  install_dependencies()
  if args.process == "nginx":
    port = setup_nginx_container()
  else if args.process == "memcached":
    port = setup_memcached_container()
  return port

def destroy_docker(args):
  if args.process == "nginx":
    destroy_nginx_container()

def run_docker_benchmarks(args, port, measure_performance):
  if args.process == "nginx":
    run_nginx_benchmark(400, 12, 10, port, measure_performance)

if __name__ == '__main__':
  parser = argparse.ArgumentParser()
  parser.add_argument('-p', '--process', required=True, help='Indicate which process to run on docker (NGINX, Spark, etc)')
  parser.add_argument('-t', '--task', required=True, help='What task to run (benchmark, attack)')
  args = parser.parse_args()

  port = setup_docker(args)
  if args.task == "benchmark":
    run_docker_benchmarks(args, port, True)
  destroy_docker(args)
