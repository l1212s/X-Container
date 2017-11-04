import plotly.plotly as py
import plotly.graph_objs as go

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

def parse_arguments():
  parser = argparse.ArgumentParser()
  parser.add_argument('-d', '--docker', required=True, help='Docker folder to use')
  parser.add_argument('-l', '--linux', required=True, help='Linux folder to use')
  parser.add_argument('-m', '--metric', required=True, help='Metric to graph')
  parser.add_argument('-p', '--process', required=True, help='Application to graph')
  parser.add_argument('-x', '--xcontainer', required=True, help='X-Container folder to use')
  args = parser.parse_args()
  return args

def create_graph(args):
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
    date.append(trace)
  layout = dict(title = mm['name'], xaxis = dict(title = mm['x-axis']), yaxis = dict(title = mm['yaxis']))
  fig = dict(data=data, layout=layout)
  py.iplot(fig, filename='test') # TODO: Change to a better name

def main():
  args = parse_arguments()
  create_graph(args)

if __name__ == '__main__':
  main()
