import argparse
import json
import plotly
import plotly.graph_objs as go
import plotly.plotly as py
import util

CONTAINERS = ['linux', 'docker', 'xcontainer']

def metric_values(name, xaxis, yaxis, mode):
  return {
    'mode': mode,
    'name': name,
    'x-axis': xaxis,
    'y-axis': yaxis,
  }

METRIC_MAP = {
  'throughput': metric_values('Throughput', 'Requests Per Second', 'Throughput', 'lines+markers'),
  'avg_latency': metric_values('Average Latency', 'Throughput', 'Average Latency (usecs)', 'markers'),
  'tail_latency': metric_values('Tail Latency', 'Throughput', 'Tail Latency (usecs)', 'markers'),
  'missed_sends': metric_values('Missed Sends', 'Requests Per Second', 'Missed Sends (%)', 'lines+markers'),
}

def title(name, process, instances, benchmark):
  n = '{0:s} ({1:s})'.format(name, benchmark)
  if process == 'memcached':
    plural = ""
    if instances > 1:
      plural = "s"
    return '{0:s} ({1:d} concurrent instance{2:s})'.format(n, instances, plural)
  else:
    return n 

def fetch_points(process, container, dates, metric):
  container_folder = util.container_folder(process, container)
  instance_folders = map(lambda d: util.instance_folder(container_folder, d), dates)
  files = map(lambda i: open('{0:s}/{1:s}.csv'.format(i, metric)), instance_folders)
  lines = map(lambda f: f.readlines(), files)
  num_lines = len(lines[0])
  points = []

  for i in range(num_lines):
    total = 0.0
    x = 0
    for l in lines:
      line = l[i].strip()
      [x,y] = line.split(',')
      total += float(y)
    points.append((x, total / float(len(dates))))
  points = sorted(points, key=lambda point: point[0])
  return points

def create_json_graph(args):
  mm = METRIC_MAP[args.metric]
  data = []
  with open('json/{0:s}'.format(args.json)) as f:
    traces = json.load(f)
  for trace in traces['traces']:
    points = fetch_points(trace['process'], trace['container'], trace['dates'], args.metric)
    
    xs = map(lambda p: p[0], points)
    ys = map(lambda p: p[1], points)

    trace = go.Scatter(
      x = xs,
      y = ys,
      mode = mm['mode'],
      name = trace['name'],
    )
    data.append(trace)

  layout = dict(title = '{0:s} ({1:s})'.format(traces['title'], args.metric), xaxis = dict(title = mm['x-axis']), yaxis = dict(title = mm['y-axis']))
  fig = dict(data=data, layout=layout)
  filename = args.json
  py.plot(fig, filename=filename)

def create_container_graph(args):
  mm = METRIC_MAP[args.metric]
  data = []
  folders = {}

  for container in CONTAINERS:
    date = getattr(args, container)
    points = fetch_points(args.process, container, [date], args.metric)

    xs = map(lambda p: p[0], points)
    ys = map(lambda p: p[1], points)

    trace = go.Scatter(
      x = xs,
      y = ys,
      mode = mm['mode'],
      name = '{0:s} ({1:s})'.format(container, date)
    )
    data.append(trace)

  layout = dict(title = title(mm['name'], args.process, args.instances, args.test), xaxis = dict(title = mm['x-axis']), yaxis = dict(title = mm['y-axis']))
  fig = dict(data=data, layout=layout)
  filename = '{0:s}-{1:s}-t-{2:s}-i{3:d}'.format(args.process, args.metric, args.test, args.instances)
  py.plot(fig, filename=filename)

def parse_arguments():
  parser = argparse.ArgumentParser()
  parser.add_argument('-t', '--test', help='Type of test (bare, CPU)')
  parser.add_argument('-d', '--docker', help='Docker folder to use')
  parser.add_argument('-j', '--json', help='JSON file to load')
  parser.add_argument('-l', '--linux', help='Linux folder to use')
  parser.add_argument('-m', '--metric', required=True, help='Metric to graph')
  parser.add_argument('-p', '--process', help='Application to graph')
  parser.add_argument('-x', '--xcontainer', help='X-Container folder to use')
  parser.add_argument('-i', '--instances', type=int, default=1, help='Number of concurrent instances of benchmark running')
  args = parser.parse_args()

  if args.json is None:
    if args.linux is None or args.docker is None or args.xcontainer is None:
      raise Exception('Need to specify folder for linux, docker and xcontainer')
    if args.process is None:
      raise Exception('Need to specify process being graphed')
    util.check_benchmark(args)

  return args

def main():
  args = parse_arguments()
  plotly.tools.set_credentials_file(username='saj9191', api_key='4VpEqUTtpT2fNnTWmXmZ')
  if args.metric == 'all':
    for metric in METRIC_MAP.keys():
      args.metric = metric
      if args.json:
  	create_json_graph(args)
      else:
        create_container_graph(args)
  else:
    if args.json:	
      create_json_graph(args)
    else:
      create_container_graph(args)

if __name__ == '__main__':
  main()
