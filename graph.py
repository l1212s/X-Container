import argparse
import plotly
import plotly.graph_objs as go
import plotly.plotly as py
import util

CONTAINERS = ['linux', 'docker', 'xcontainer']

def metric_values(name, xaxis, yaxis):
  return {
    'name': name,
    'x-axis': xaxis,
    'y-axis': yaxis,
  }

METRIC_MAP = {
  'throughput': metric_values('Throughput', 'Requests Per Second', 'Throughput'),
  'avg_latency': metric_values('Average Latency', 'Throughput', 'Average Latency (usecs)'),
}

def title(name, process, instances):
  if process == 'memcached':
    plural = ""
    if instances > 1:
      plural = "s"
    return '{0:s} ({1:d} concurrent instance{2:s})'.format(name, instances, plural)
  else:
    return name   

def parse_arguments():
  parser = argparse.ArgumentParser()
  parser.add_argument('-d', '--docker', required=True, help='Docker folder to use')
  parser.add_argument('-l', '--linux', required=True, help='Linux folder to use')
  parser.add_argument('-m', '--metric', required=True, help='Metric to graph')
  parser.add_argument('-p', '--process', required=True, help='Application to graph')
  parser.add_argument('-x', '--xcontainer', required=True, help='X-Container folder to use')
  parser.add_argument('-i', '--instances', type=int, default=1, help='Number of concurrent instances of benchmark running')
  args = parser.parse_args()
  return args

def create_graph(args):
  plotly.tools.set_credentials_file(username='saj9191', api_key='4VpEqUTtpT2fNnTWmXmZ')
  mm = METRIC_MAP[args.metric]
  data = []
  folders = {}

  for container in CONTAINERS:
    date = getattr(args, container)
    folder = util.instance_folder(util.container_folder(args.process, container), date)
    f = open('{0:s}/{1:s}.csv'.format(folder, args.metric))
    xs = []
    ys = []
    for line in f.readlines():
      line = line.strip()
      [x,y] = line.split(',')
      xs.append(x)
      ys.append(y)

    trace = go.Scatter(
      x = xs,
      y = ys,
      mode = 'lines+markers',
      name = '{0:s} ({1:s})'.format(container, date)
    )
    data.append(trace)

  layout = dict(title = title(mm['name'], args.process, args.instances), xaxis = dict(title = mm['x-axis']), yaxis = dict(title = mm['y-axis']))
  fig = dict(data=data, layout=layout)
  filename = '{0:s}-{1:s}-x{2:s}-d{3:s}-l{4:s}'.format(args.process, args.metric, args.xcontainer, args.docker, args.linux)
  py.iplot(fig, filename=filename)

def main():
  args = parse_arguments()
  create_graph(args)

if __name__ == '__main__':
  main()
