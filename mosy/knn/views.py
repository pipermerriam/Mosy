from django.shortcuts import render_to_response, get_object_or_404
from django.template import RequestContext
from django.db import connection, transaction

from mosy.knn.models import LSH

def index(request):
  template = 'result.html'
  this_lsh = get_object_or_404(LSH, pk = lsh_id)
  data = {'lsh': this_lsh}

  context = RequestContext(request)
  return render_to_response(template, data, context)
  template = 'index.html'

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

