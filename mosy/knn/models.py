from django.db import models
from django.db.models import Q

from mosy.pof.fields import PickledObjectField

from random import normalvariate, uniform, randint, shuffle, sample
from math import sqrt, floor
from threading import Thread
from time import time

# Create your models here.

class DataPoint(models.Model):
  vector = PickledObjectField()

  def get_knn(self, points = None, debug = False):
    if not points:
      points = DataPoint.objects.all()
    neighbors = []
    for dp in points:
      if dp.id == self.id:
        continue
      dp.distance = self.dist(dp)
      if len(neighbors) < 20 or dp.distance < neighbors[0].distance:
        neighbors.append(dp)
        neighbors = sorted(neighbors, key = lambda p: p.distance)
        neighbors = neighbors[:20]
        neighbors.reverse()
        if debug:
          print "New Neighbor: %i - %f"%(dp.id, dp.distance)
    for n in neighbors:
      if self.id < n.id:
        a = self
        b = n
      else:
        a = n
        b = self
      Edge.objects.get_or_create(point_a = a, point_b = b, length = a.dist(b))
    return neighbors

  def dist(self, other, exact = False):
    d = 0
    for a, b in zip(self.vector, other.vector):
      d += (a-b)**2
    return sqrt(d)

class Edge(models.Model):
  point_a = models.ForeignKey(DataPoint, related_name = '+')
  point_b = models.ForeignKey(DataPoint, related_name = '+')
  length = models.FloatField()

  class Meta:
    unique_together = ('point_a', 'point_b')

class LSH(models.Model):
  parent = models.ForeignKey('self', related_name = 'children', null = True)
  score = models.FloatField(null = True)

  a = PickledObjectField(null = True)
  r = models.IntegerField(null = True)
  b = models.FloatField(null = True)
  mean = models.FloatField(null = True)
  std = models.FloatField(null = True)

  @classmethod
  def evolve(cls):
    while True:
      if cls.objects.count() < 1000:
        print "Generating Base Objects"
        tlist = []
        for i in range(1000-cls.objects.count()):
          x = cls()
          x.test()
      null_query = cls.objects.filter(score = None)
      if null_query.exists():
        print "Scoring New Children"
        for lsh in null_query:
          lsh.test()
      best_query = cls.objects.order_by('-score')[:20]
      for lsh in best_query:
        print "Mutating LSH(%i) - Score:%f"%(lsh.id, lsh.score)
        for i in range(50):
          lsh.mutate()

  def generate(self, mean = None, std = None, dimension = 48):
    if not mean == None:
      self.mean = mean
    else:
      self.mean = floor(uniform(128, 2048))
    if not std == None:
      self.std = std
    else:
      self.std = floor(uniform(8, 1024))
    self.a = [normalvariate(self.mean, self.std) for i in range(dimension)]
    self.r = floor(uniform(32, 16384))
    self.b = uniform(0, self.r)
    self.save()

  def project(self, v):
    if not self.a or not self.b or not self.r:
      self.generate()
    dp = sum([a*x for a, x in zip(self.a, v)])
    return floor((dp + self.b)/float(self.r))

  def test(self, early_exit = False):
    start_time = time()
    #sample_set = list(DataPoint.objects.only('id').order_by('?').values_list('id', flat=True)[:200])
    sample_set = sample(range(1, 5001), 200)
    overall_score = 0.0
    if early_exit:
      target_score = LSH.objects.order_by('-score')[0].score

    for n in range(len(sample_set)):
      test_point = DataPoint.objects.get(pk = sample_set.pop())

      close_points = list(Edge.objects.filter(point_a = test_point).order_by('length').values_list('point_b', 'length'))
      close_points += list(Edge.objects.filter(point_b = test_point).order_by('length').values_list('point_a', 'length'))
      close_points = sorted(close_points, key = lambda val: val[1])[:20]
      close_points = [j[0] for j in close_points]
      assert len(close_points) == 20

      points = range(1, 5001)
      for point in close_points:
        points.remove(point)
      points.remove(test_point.id)
      points = sample(points, 200)
      points += close_points
      points = list(DataPoint.objects.filter(pk__in = points))
      for p in points:
        p.distance = test_point.dist(p)

      for point in points:
        point.projection = self.project(point.vector)

      shuffle(points)
      points = sorted(points, key = lambda p: p.projection)
      for i in range(220):
        point = points[i]
        point.p_rank = i

      score = 72
      points = sorted(points, key = lambda p: p.distance)
      for i in range(20):
        point = points[i]
        point.rank = i
        if abs(point.rank - point.p_rank) > 5:
          score -= 20.0/(point.rank + 1)
      #print "Test %i: Score -> %i"%(i, int(score))
      overall_score = (overall_score*n+score)/(n+1)
      if early_exit and n > 80:
        if overall_score < target_score*(float(n)/200-0.2):
          print "Early Exit Criteria Met at %i"%n
          break

    self.score = overall_score
    self.save()

    if self.parent:
      print "Parent(%i) Score: %f"%(self.parent.id, self.parent.score)
    print "LSH(%i) - Overall Score: %f Test_Time: %f"%(self.id, overall_score, time() - start_time)

  def mutate(self):
    a = self.a
    b = self.b
    r = self.r
    mean = self.mean
    std = self.std

    x = randint(1, len(a)+4)
    if x <= 2:
      if x == 1:
        mean = floor(uniform(128, 2048))
      if x == 2:
        std = floor(uniform(64, 1024))
      a = [normalvariate(self.mean, self.std) for i in range(len(self.a))]
    if x == 3:
      b = uniform(0, r)
    if x == 4:
      r = floor(uniform(b, 16384))
    if x >= 5:
      a[randint(0, len(a)-1)] = normalvariate(self.mean, self.std)
    return LSH.objects.create(
      parent = self,
      a = a,
      b = b,
      r = r,
      mean = mean,
      std = std)
