import subprocess

def install_dependencies():
  subprocess.call(["apt-get", "install", "linux-tools-generic"])
  subprocess.call(["apt-get", "install", "make"])
  subprocess.call(["apt-get", "install", "gcc"])
  subprocess.call(["apt-get", "install", "-y", "docker-ce"])
  subprocess.call(["git", "clone", "https://github.com/wg/wrk.git"])

def setup_nginx_configuration(configuration_file_path):
  configuration = """
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
"""
  f = open(configuration_file_path, "w")
  f.write(configuration)
  f.close

def setup_nginx_container():
  configuration_file_path = "/dev/nginx.conf"
  setup_nginx_configuration(configuration_file_path)

  subprocess.call([
    "docker", "run", "--name", "nginx_container",
    "-P", "-v", configuration_file_path + ":/etc/nginx/nginx.conf:ro",
    "-d", "nginx"
  ])

  output = subprocess.check_output(["docker", "ps"])
  results = re.findall("0.0.0.0:([0-9]+)->80/tcp", output)
  port = results[0]
  return port

def run_nginx_benchmark(num_connections, num_threads, duration, port, measure_performance):
  command = [
    "./wrk",
    "-t" + num_threads,
    "-c" + num_connections,
    "-d" + duration + "s",
    "http://localhost:" + port + "/index.html"
  ]
  if measure_performance:
    command = command + ["perf", "stat"]
  subprocess.call(command)

def setup_docker():
  install_dependencies()
  nginx_port = setup_nginx_container()
  return nginx_port

def run_docker_benchmarks(nginx_port, measure_performance):
  run_nginx_benchmark(400, 12, 10, nginx_port, measure_performance)

if __name__ == '__main__':
  nginx_port = setup_docker()
  run_docker_benchmarks(nginx_port, true)
