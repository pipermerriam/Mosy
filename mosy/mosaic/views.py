from django.shortcuts import render_to_response, get_object_or_404
from django.template import RequestContext
from django.db import connection, transaction

from mosy.mosaic.models import StockImage, Tile, CompareMethod, CompareTest

# Create your views here.
def compare(request):
  if request.method == 'POST':
    pass
  template = 'compare_test.html'
  data = {}

  if CompareTest.objects.filter(winner = None):
    this_ct = CompareTest.objects.filter(winner = None).order_by('?')[:1].get()
  else:
    this_ct = CompareTest.generate(1)

  data['target_map'] = this_ct.target.pixel_map
  data['a_map'] = this_ct.tile_a.pixel_map
  data['b_map'] = this_ct.tile_b.pixel_map

  context = RequestContext(request)
  return render_to_response(template, data, context)
