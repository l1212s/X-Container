import subprocess

def shell_call(command, show_command=False):
  if show_command:
    print('RUNNING COMMAND: ' + command)
  p = subprocess.Popen(command, shell=True)
  p.wait()
  if show_command:
    print('')

def container_folder(process, container):
  return "benchmark/{0:s}-{1:s}".format(process, container)

def instance_folder(cf, date):
  return "{0:s}/{1:s}".format(cf, date)
