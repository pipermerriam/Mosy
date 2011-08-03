from django.shortcuts import render_to_response, get_object_or_404
from django.template import RequestContext
from django.db import connection, transaction

from mosy.knn.models import LSH, DataPoint

def index(request):
  template = 'index.html'
  data = {}
  top_lsh_query = LSH.objects.raw('SELECT id, collisions, a, b, r, mean, std, p1, p2 FROM knn_lsh ORDER BY p1-p2 DESC LIMIT 0, 50')
  top_lsh = [lsh for lsh in top_lsh_query]

  data['top_lsh'] = top_lsh

  context = RequestContext(request)
  return render_to_response(template, data, context)

def detail(request, lsh_id):
  template = 'result.html'
  this_lsh = get_object_or_404(LSH, pk = lsh_id)
  data = {}
  data['lsh'] = this_lsh
  data['score'] = this_lsh.score
  data['generation'] = this_lsh.generation
  data['father'] = this_lsh.father
  data['mother'] = this_lsh.mother

  context = RequestContext(request)
  return render_to_response(template, data, context)

def datapoint(request, dp_id):
  template = 'datapoint.html'
  this_dp = get_object_or_404(LSH, pk = dp_id)
  data = {}
  data['dp'] = this_dp
  data['pixel_map'] = this_dp.pixel_map

  context = RequestContext(request)
  return render_to_response(template, data, context)
  

