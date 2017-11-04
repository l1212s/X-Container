import subprocess


def shell_call(command, show_command=False):
  if show_command:
    print('RUNNING COMMAND: ' + command)
  p = subprocess.Popen(command, shell=True)
  p.wait()
  if show_command:
    print('')
