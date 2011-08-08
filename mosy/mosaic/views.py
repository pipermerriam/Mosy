from django.shortcuts import render_to_response, get_object_or_404
from django.template import RequestContext
from django.db import connection, transaction
from django.http import HttpResponseRedirect

from mosy.mosaic.models import StockImage, Tile, CompareMethod, CompareTest

# Create your views here.
def compare(request):
  template = 'compare_test.html'
  data = {}

  test_id = int(request.GET.get('id', 0))
  if test_id:
    res = request.GET.get('w', False)
    if res:
      this_test = CompareTest.objects.get(pk = test_id)
      if res == 'a':
        this_test.winner = this_test.method_a
      elif res == 'b':
        this_test.winner = this_test.method_b
      elif res == 'c':
        this_test.delete()
        return HttpResponseRedirect('/compare/')
      if this_test.winner:
        this_test.save()
        return HttpResponseRedirect('/compare/')

  if CompareTest.objects.filter(winner = None):
    this_ct = CompareTest.objects.filter(winner = None).order_by('?')[:1].get()
  else:
    this_ct = None

  data['remaining'] = CompareTest.objects.filter(winner = None).count()
  if this_ct:
    data['test_id'] = this_ct.id
    data['target_map'] = this_ct.target.pixel_map
    data['a_map'] = this_ct.tile_a.pixel_map
    data['b_map'] = this_ct.tile_b.pixel_map

  context = RequestContext(request)
  return render_to_response(template, data, context)

def tile(request, tile_id):
  template = 'tile.html'
  data = {}

  this_tile = get_object_or_404(Tile, pk=tile_id)

  data['original'] = this_tile.origin
  data['tile'] = this_tile
  data['pixel_map'] = this_tile.pixel_map

  context = RequestContext(request)
  return render_to_response(template, data, context)
