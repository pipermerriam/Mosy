from django.db import models
from django.db.models import Q, F

from mosy.pof.fields import PickledObjectField

from random import normalvariate, uniform, randint, shuffle, sample
from math import sqrt, floor
from threading import Thread
from time import time

# Create your models here.

RADIUS = 300
TOLERANCE = 1.2

class DataPoint(models.Model):
  vector = PickledObjectField()

  @classmethod
  def get_plist(cls):
    plist = {}
    for p in cls.objects.iterator():
      p.neighbors = Neighbors.objects.get(point = p).neighbors
      plist[p.id] = p
    return plist

  def get_knn(self, points = None, debug = False):
    if not points:
      points = DataPoint.objects.all()
    neighbors = []
    for dp in points:
      if dp.id == self.id:
        continue
      dp.distance = self.dist(dp)
      if len(neighbors) < 200 or dp.distance < neighbors[0].distance:
        neighbors.append(dp)
        neighbors = sorted(neighbors, key = lambda p: p.distance)
        neighbors = neighbors[:200]
        neighbors.reverse()
        if debug:
          print "New Neighbor: %i - %f"%(dp.id, dp.distance)
    nl = [n.id for n in neighbors]
    n, created = Neighbors.objects.get_or_create(point = self)
    if created:
      n.neighbors = nl
      n.save()
    return neighbors

  def dist(self, other, exact = False):
    d = 0
    for a, b in zip(self.vector, other.vector):
      d += (a-b)**2
    return sqrt(d)

class Neighbors(models.Model):
  point = models.ForeignKey(DataPoint)
  neighbors = PickledObjectField()

class LSH(models.Model):
  parent = models.ForeignKey('self', related_name = 'children', null = True)
  score = models.FloatField(null = True)
  p1 = models.FloatField(null = True)
  p2 = models.FloatField(null = True)
  collisions = models.FloatField(null = True)

  a = PickledObjectField(null = True)
  r = models.IntegerField(null = True)
  b = models.FloatField(null = True)
  mean = models.FloatField(null = True)
  std = models.FloatField(null = True)

  @classmethod
  def evolve(cls):
    plist = DataPoint.get_plist()
    while True:
      if cls.objects.count() < 10000:
        if cls.objects.filter(score = None):
          for x in cls.objects.filter(score = None):
            x.test(plist = plist)
        print "Generating Base Objects"
        for i in range(10000-cls.objects.count()):
          x = cls()
          x.test(plist = plist)
      null_query = cls.objects.filter(score = None)
      if null_query.exists():
        print "Scoring New Children"
        for lsh in null_query:
          lsh.test(plist = plist)
      best_query = cls.objects.order_by('-score')[:20]
      for lsh in best_query:
        print "Mutating LSH(%i) - Score:%f"%(lsh.id, lsh.score)
        for i in range(50):
          lsh.mutate()

  def generate(self, mean = None, std = None, dimension = 48):
    if not mean == None:
      self.mean = mean
    else:
      self.mean = floor(uniform(2, 128))
    if not std == None:
      self.std = std
    else:
      self.std = floor(uniform(1, 64))
    self.a = [normalvariate(self.mean, self.std) for i in range(dimension)]
    self.r = floor(uniform(2, 16384))
    self.b = uniform(0, self.r)
    self.save()

  def project(self, v):
    if not self.a or not self.b or not self.r:
      self.generate()
    dp = sum([a*x for a, x in zip(self.a, v)])
    return floor((dp + self.b)/float(self.r))

  def test(self, plist = None, early_exit = False):
    if plist == None:
      plist = DataPoint.get_plist()
    start_time = time()
    sample_set = sample(range(1, 5001), 200)
    score_overall = 0.0
    p1_overall = 0.0
    p2_overall = 0.0
    p3_overall = 0.0
    collisions_overall = 0.0

    for n in range(len(sample_set)):
      #test_point = DataPoint.objects.get(pk = sample_set.pop())
      test_point = plist[sample_set.pop()]
      test_point.projection = self.project(test_point.vector)

      #close_points = Neighbors.objects.get(point = test_point).neighbors
      close_points = test_point.neighbors

      points = range(1, 5001)
      for point in close_points:
        points.remove(point)
      points.remove(test_point.id)
      points = sample(points, 200)
      points += close_points
      points = [plist[p] for p in points]
      #points = list(DataPoint.objects.filter(pk__in = points))

      assert len(points) == 400
      for p in points:
        p.distance = test_point.dist(p)

      for point in points:
        point.projection = self.project(point.vector)

      shuffle(points)
      points = sorted(points, key = lambda p: p.projection)
      for i in range(400):
        point = points[i]
        point.p_rank = i


      score = 120
      points = sorted(points, key = lambda p: p.distance)

      collisions = 0
      p1_count = 0
      p2_count = 0
      p3_count = 0
      for i in range(400):
        point = points[i]
        point.rank = i
        if i < 200 and abs(point.rank - point.p_rank) > 5:
          score -= 20.0/(point.rank + 1)
        if test_point.projection == point.projection:
          collisions += 1
          if point.distance <= RADIUS:
            p1_count += 1
          elif point.distance >= RADIUS*TOLERANCE:
            p2_count += 1
          else:
            p3_count += 1
      score_overall = (score_overall*n+score)/(n+1)
      p1_overall = (p1_overall*n+p1_count)/(n+1)
      p2_overall = (p2_overall*n+p2_count)/(n+1)
      p3_overall = (p3_overall*n+p3_count)/(n+1)
      collisions_overall = (collisions_overall*n+collisions)/(n+1)

    self.collisions = collisions_overall
    if collisions_overall > 0:
      self.p1 = p1_overall
      self.p2 = p2_overall
    self.score = score_overall
    self.save()

    if self.parent:
      print "Parent(%i) Score: %f"%(self.parent.id, self.parent.score)
    print "LSH(%i) - Overall Score: %f Test_Time: %f"%(self.id, score_overall, time() - start_time)
    print "Colisions: %i - P1: %i P2: %i P3: %i"%(int(collisions_overall), int(p1_overall), int(p2_overall), int(p3_overall))

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
